from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

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
        service = AsyncMock()
        page_filter = FilterPage.build(name="Electric Company")

        await create(service, user, create_institution_payload)
        await list_all(service, user, page_filter)
        await find_one("institution-id", service, user)
        await update(service, "institution-id", user, update_institution_payload)
        await delete(service, "institution-id", user)

        service.create.assert_awaited_once_with(
            user=user, payload=create_institution_payload
        )
        service.list_all.assert_awaited_once_with(page_filter=page_filter, user=user)
        service.find_by.assert_awaited_once_with(
            id="institution-id", user_request=user.username, user_id=user.id
        )
        service.update.assert_awaited_once_with(
            institution_id="institution-id", payload=update_institution_payload, user=user
        )
        service.delete.assert_awaited_once_with(user=user, institution_id="institution-id")

    @staticmethod
    def test_delete_endpoint_preserves_service_response(user):
        app = FastAPI()
        app.include_router(router, prefix="/institutions")
        service = AsyncMock()
        service.delete.return_value = Message(message="Deleted")
        app.dependency_overrides[institution_service] = lambda: service
        app.dependency_overrides[get_current_user] = lambda: user

        with TestClient(app) as client:
            response = client.delete("/institutions/institution-id")

        assert response.status_code == 200
        assert response.json() == {"message": "Deleted"}
