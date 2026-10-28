from unittest.mock import AsyncMock
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest

from app.core.database import get_session
from app.core.security import get_current_user
from app.domain.institution.route import (
    create,
    delete,
    find_one,
    list_all,
    institution_filter,
    institution_service,
    router,
    update,
)
from app.domain.institution.service import InstitutionService
from app.shared.schemas import FilterPage, Message


def test_institution_service_builds_from_session():
    assert isinstance(institution_service(AsyncMock()), InstitutionService)


def test_institution_filter_builds_dynamic_filter():
    page_filter = institution_filter(page=1, name="Electric Company", limit=12)

    assert page_filter.page == 1
    assert page_filter.name == "Electric Company"
    assert page_filter.limit == 12


class TestInstitutionRoutes:
    @staticmethod
    def test_create_endpoint_requires_authentication():
        app = FastAPI()
        app.include_router(router, prefix="/institutions")
        service = AsyncMock()
        app.dependency_overrides[institution_service] = lambda: service

        with TestClient(app) as client:
            response = client.post("/institutions", json={"name": "Electric Company"})

        assert response.status_code in (401, 403)
        service.create.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_crud_routes_delegate_with_authenticated_user(
        user, create_institution_payload, update_institution_payload
    ):
        resource_id = uuid4()
        service = AsyncMock()
        page_filter = FilterPage.build(name="Electric Company")

        await create(service, user, create_institution_payload)
        await list_all(service, user, page_filter)
        await find_one(resource_id, service, user)
        await update(service, resource_id, user, update_institution_payload)
        await delete(service, resource_id, user)

        service.create.assert_awaited_once_with(
            user=user, payload=create_institution_payload
        )
        service.list_all.assert_awaited_once_with(page_filter=page_filter, user=user)
        service.find_by.assert_awaited_once_with(filters={"id": resource_id}, user=user)
        service.update.assert_awaited_once_with(
            identifier=resource_id,
            payload=update_institution_payload,
            user=user,
        )
        service.delete.assert_awaited_once_with(user=user, identifier=resource_id)

    @staticmethod
    def test_delete_endpoint_preserves_service_response(user):
        app = FastAPI()
        app.include_router(router, prefix="/institutions")
        service = AsyncMock()
        service.delete.return_value = Message(message="Deleted")
        app.dependency_overrides[institution_service] = lambda: service
        app.dependency_overrides[get_current_user] = lambda: user

        with TestClient(app) as client:
            response = client.delete(f"/institutions/{uuid4()}")
            malformed = client.delete("/institutions/not-a-uuid")

        assert response.status_code == 200
        assert response.json() == {"message": "Deleted"}
        assert malformed.status_code == 422


@pytest.mark.asyncio
async def test_http_crud_with_real_institution_service_and_database(
    institution_session, institution_cache, user
):
    app = FastAPI()
    app.include_router(router, prefix="/institutions")

    async def session_override():
        yield institution_session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_current_user] = lambda: user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/institutions", json={"name": " Electric Company "}
        )
        assert created.status_code == 201
        body = created.json()
        identifier = body["id"]
        assert body["name"] == "Electric Company"
        assert set(body) == {"id", "name", "created_at", "updated_at", "deleted_at"}
        assert (await client.get(f"/institutions/{identifier}")).json() == body
        page = await client.get(
            "/institutions",
            params={"offset": 0, "limit": 1, "name": "Electric Company"},
        )
        assert page.status_code == 200
        assert page.json()["meta"]["total"] == 1
        assert page.json()["items"] == [body]
        assert (
            await client.post("/institutions", json={"name": "electric company"})
        ).status_code == 409
        updated = await client.put(
            f"/institutions/{identifier}", json={"name": "Water Company"}
        )
        assert updated.json() == {
            "message": f"Update Institution {identifier} successfully"
        }
        assert (await client.get(f"/institutions/{identifier}")).json()[
            "name"
        ] == "Water Company"
        assert (
            await client.put(f"/institutions/{identifier}", json={"name": None})
        ).status_code == 422
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=uuid4(), username="other"
        )
        for method in ("get", "put", "delete"):
            kwargs = {"json": {"name": "No"}} if method == "put" else {}
            assert (
                await getattr(client, method)(f"/institutions/{identifier}", **kwargs)
            ).status_code == 404
        assert (await client.get("/institutions")).json() == []
        app.dependency_overrides[get_current_user] = lambda: user
        deleted = await client.delete(f"/institutions/{identifier}")
        assert deleted.json() == {
            "message": f"Delete Institution {identifier} successfully"
        }
        assert (await client.get(f"/institutions/{identifier}")).status_code == 404
        assert (await client.delete(f"/institutions/{identifier}")).status_code == 404
