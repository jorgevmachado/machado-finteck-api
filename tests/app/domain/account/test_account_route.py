from unittest.mock import AsyncMock
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest

from app.core.database import get_session
from app.core.security import get_current_user
from app.domain.account.route import (
    account_filter,
    account_service,
    create,
    delete,
    find_one,
    list_all,
    router,
    update,
)
from app.domain.account.service import AccountService
from app.models import AccountTypeEnum
from app.shared.schemas import FilterPage, Message


def test_account_service_builds_from_session():
    assert isinstance(account_service(AsyncMock()), AccountService)


def test_account_filter_builds_dynamic_filter():
    page_filter = account_filter(page=1, name="Principal", limit=12, clean_cache=True)

    assert page_filter.page == 1
    assert page_filter.name == "Principal"
    assert page_filter.limit == 12
    assert page_filter.clean_cache


def test_account_filter_passes_type_and_active_and_drops_legacy_with_deleted():
    page_filter = account_filter(
        page=1,
        name="Principal",
        type=AccountTypeEnum.CASH,
        is_active=True,
        agency="1234",
        account_number="123456789",
        financial_institution="Nubank",
        limit=5,
        offset=0,
    )

    assert page_filter.type == AccountTypeEnum.CASH
    assert page_filter.is_active is True
    assert page_filter.agency == "1234"
    assert page_filter.account_number == "123456789"
    assert page_filter.financial_institution == "Nubank"
    assert not hasattr(page_filter, "with_deleted")


class TestAccountRoutes:
    @staticmethod
    def test_create_endpoint_requires_authentication():
        app = FastAPI()
        app.include_router(router, prefix="/accounts")
        service = AsyncMock()
        app.dependency_overrides[account_service] = lambda: service

        with TestClient(app) as client:
            response = client.post("/accounts", json={"name": "Principal"})

        assert response.status_code in (401, 403)
        service.create.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_crud_routes_delegate_with_authenticated_user(
        user, create_account_payload, update_account_payload
    ):
        resource_id = uuid4()
        service = AsyncMock()
        page_filter = FilterPage.build(name="Principal")

        await create(service, user, create_account_payload)
        await list_all(service, user, page_filter)
        await find_one(resource_id, service, user)
        await update(service, resource_id, user, update_account_payload)
        await delete(service, resource_id, user)

        service.create.assert_awaited_once_with(
            user=user, payload=create_account_payload
        )
        service.list_all.assert_awaited_once_with(page_filter=page_filter, user=user)
        service.find_by.assert_awaited_once_with(filters={"id": resource_id}, user=user)
        service.update.assert_awaited_once_with(
            identifier=resource_id,
            payload=update_account_payload,
            user=user,
        )
        service.delete.assert_awaited_once_with(user=user, identifier=resource_id)

    @staticmethod
    def test_delete_endpoint_preserves_service_response(user):
        app = FastAPI()
        app.include_router(router, prefix="/accounts")
        service = AsyncMock()
        service.delete.return_value = Message(message="Deleted")
        app.dependency_overrides[account_service] = lambda: service
        app.dependency_overrides[get_current_user] = lambda: user
        account_id = uuid4()

        with TestClient(app) as client:
            response = client.delete(f"/accounts/{account_id}")
            malformed = client.delete("/accounts/not-a-uuid")

        assert response.status_code == 200
        assert response.json() == {"message": "Deleted"}
        assert malformed.status_code == 422


@pytest.mark.asyncio
async def test_http_crud_with_real_account_service_and_database(
    account_session, account_cache, user
):
    app = FastAPI()
    app.include_router(router, prefix="/accounts")

    async def session_override():
        yield account_session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_current_user] = lambda: user
    payload = {
        "name": "Principal",
        "type": "CASH",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post("/accounts", json=payload)
        assert created.status_code == 201
        body = created.json()
        identifier = body["id"]
        assert body["name"] == "Principal"
        assert body["type"] == "CASH"
        assert (await client.get(f"/accounts/{identifier}")).json() == body
        page = await client.get(
            "/accounts",
            params={"offset": 0, "limit": 1, "name": "Principal"},
        )
        assert page.status_code == 200
        assert page.json()["meta"]["total"] == 1
        assert page.json()["items"] == [body]
        assert (await client.post("/accounts", json=payload)).status_code == 409
        updated = await client.put(f"/accounts/{identifier}", json={"color": "Blue"})
        assert updated.json() == {
            "message": f"Update Account {identifier} successfully"
        }
        assert (await client.get(f"/accounts/{identifier}")).json()["color"] == "Blue"
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=uuid4(), username="other"
        )
        for method in ("get", "put", "delete"):
            kwargs = {"json": {"color": "No"}} if method == "put" else {}
            assert (
                await getattr(client, method)(f"/accounts/{identifier}", **kwargs)
            ).status_code == 404
        assert (await client.get("/accounts")).json() == []
        app.dependency_overrides[get_current_user] = lambda: user
        deleted = await client.delete(f"/accounts/{identifier}")
        assert deleted.json() == {
            "message": f"Delete Account {identifier} successfully"
        }
        assert (await client.get(f"/accounts/{identifier}")).status_code == 404
        assert (await client.delete(f"/accounts/{identifier}")).status_code == 404
