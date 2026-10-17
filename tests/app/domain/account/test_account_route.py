from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.domain.account.route import (
    account_filter,
    account_service,
    create,
    find_one,
    list_all,
    router,
    update,
)
from app.domain.account.schema import AccountUpdateSchema
from app.domain.account.service import AccountService
from app.shared.schemas import FilterPage, Message

def test_account_builds_service() -> None:
    service = account_service(AsyncMock())
    assert isinstance(service, AccountService)


def test_get_account_filter_builds_dynamic_filter():
    page_filter = account_filter(
        page=1,
        name="Account Name",
        limit=12,
        clean_cache=True,
    )

    assert page_filter.page == 1
    assert page_filter.name == "Account Name"
    assert page_filter.limit == 12
    assert page_filter.clean_cache

class TestAccountRoutes:
    @staticmethod
    @pytest.mark.parametrize("status_code", [200, 404, 500])
    def test_delete_delegates_to_service_and_preserves_response(user, status_code):
        app = FastAPI()
        app.include_router(router, prefix="/accounts")
        service = AsyncMock()
        if status_code == 200:
            service.delete.return_value = Message(message="Deleted")
        else:
            service.delete.side_effect = HTTPException(
                status_code=status_code, detail="Account deletion failed"
            )
        app.dependency_overrides[account_service] = lambda: service
        app.dependency_overrides[get_current_user] = lambda: user

        with TestClient(app) as client:
            response = client.delete("/accounts/account-id")

        assert response.status_code == status_code
        service.delete.assert_awaited_once_with(user=user, account_id="account-id")
        if status_code == 200:
            assert response.json() == {"message": "Deleted"}
        else:
            assert response.json() == {"detail": "Account deletion failed"}

    @staticmethod
    def test_delete_requires_authentication():
        app = FastAPI()
        app.include_router(router, prefix="/accounts")
        service = AsyncMock()
        app.dependency_overrides[account_service] = lambda: service

        with TestClient(app) as client:
            response = client.delete("/accounts/account-id")

        assert response.status_code in (401, 403)
        service.delete.assert_not_awaited()

    @staticmethod
    def test_update_accepts_payload_without_name_and_type(user):
        app = FastAPI()
        app.include_router(router, prefix="/accounts")
        service = AsyncMock()
        service.update.return_value = Message(message="Updated")
        app.dependency_overrides[account_service] = lambda: service
        app.dependency_overrides[get_current_user] = lambda: user

        with TestClient(app) as client:
            response = client.put("/accounts/account-id", json={"color": "Blue"})

        assert response.status_code == 200
        service.update.assert_awaited_once_with(
            param="account-id",
            update_schema=AccountUpdateSchema(color="Blue"),
            user=user,
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_one_route_scopes_lookup_to_authenticated_user(user):
        service = AsyncMock()
        account_id = "account-id"

        await find_one(param=account_id, service=service, current_user=user)

        service.find_by.assert_awaited_once_with(
            id=account_id,
            user_request=user.username,
            user_id=user.id,
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_route_passes_authenticated_user_to_service(user):
        service = AsyncMock()
        page_filter = FilterPage.build(name="Daily")

        await list_all(
            service=service,
            current_user=user,
            page_filter=page_filter,
        )

        service.list_all.assert_awaited_once_with(
            page_filter=page_filter,
            user=user,
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_route_passes_authenticated_user_to_service(
        user, update_account_payload
    ):
        service = AsyncMock()
        account_id = "account-id"

        await update(
            service=service,
            account_id=account_id,
            current_user=user,
            payload=update_account_payload,
        )

        service.update.assert_awaited_once_with(
            param=account_id,
            update_schema=update_account_payload,
            user=user,
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_create_route_passes_authenticated_user_and_payload_to_service(
        user, create_account_payload
    ):
        service = AsyncMock()

        await create(
            service=service,
            current_user=user,
            account_data=create_account_payload,
        )

        service.create.assert_awaited_once_with(
            user=user,
            payload=create_account_payload,
        )
