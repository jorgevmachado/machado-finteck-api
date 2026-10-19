from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.domain.credit_card.route import (
    credit_card_filter,
    credit_card_service,
    create,
    find_one,
    list_all,
    router,
    update,
)
from app.domain.credit_card.schema import CreditCardUpdateSchema
from app.domain.credit_card.service import CreditCardService
from app.shared.schemas import FilterPage, Message

def test_credit_card_builds_service() -> None:
    service = credit_card_service(AsyncMock())
    assert isinstance(service, CreditCardService)


def test_get_credit_card_filter_builds_dynamic_filter():
    page_filter = credit_card_filter(
        page=1,
        name="Credit Card Name",
        limit=12,
        clean_cache=True,
    )

    assert page_filter.page == 1
    assert page_filter.name == "Credit Card Name"
    assert page_filter.limit == 12
    assert page_filter.clean_cache

class TestCreditCardRoutes:
    @staticmethod
    @pytest.mark.parametrize("status_code", [200, 404, 500])
    def test_delete_delegates_to_service_and_preserves_response(user, status_code):
        app = FastAPI()
        app.include_router(router, prefix="/credit-cards")
        service = AsyncMock()
        if status_code == 200:
            service.delete.return_value = Message(message="Deleted")
        else:
            service.delete.side_effect = HTTPException(
                status_code=status_code, detail="Credit Card deletion failed"
            )
        app.dependency_overrides[credit_card_service] = lambda: service
        app.dependency_overrides[get_current_user] = lambda: user

        with TestClient(app) as client:
            response = client.delete("/credit-cards/credit-card-id")

        assert response.status_code == status_code
        service.delete.assert_awaited_once_with(user=user, credit_card_id="credit-card-id")
        if status_code == 200:
            assert response.json() == {"message": "Deleted"}
        else:
            assert response.json() == {"detail": "Credit Card deletion failed"}

    @staticmethod
    def test_delete_requires_authentication():
        app = FastAPI()
        app.include_router(router, prefix="/credit-cards")
        service = AsyncMock()
        app.dependency_overrides[credit_card_service] = lambda: service

        with TestClient(app) as client:
            response = client.delete("/credit-cards/credit-card-id")

        assert response.status_code in (401, 403)
        service.delete.assert_not_awaited()

    @staticmethod
    def test_update_accepts_payload_without_name_and_type(user):
        app = FastAPI()
        app.include_router(router, prefix="/credit-cards")
        service = AsyncMock()
        service.update.return_value = Message(message="Updated")
        app.dependency_overrides[credit_card_service] = lambda: service
        app.dependency_overrides[get_current_user] = lambda: user

        with TestClient(app) as client:
            response = client.put("/credit-cards/credit-card-id", json={"color": "Blue"})

        assert response.status_code == 200
        service.update.assert_awaited_once_with(
            param="credit-card-id",
            update_schema=CreditCardUpdateSchema(color="Blue"),
            user=user,
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_one_route_scopes_lookup_to_authenticated_user(user):
        service = AsyncMock()
        credit_card_id = "credit-card-id"

        await find_one(param=credit_card_id, service=service, current_user=user)

        service.find_by.assert_awaited_once_with(
            id=credit_card_id,
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
        user, update_credit_card_payload
    ):
        service = AsyncMock()
        credit_card_id = "credit-card-id"

        await update(
            service=service,
            credit_card_id=credit_card_id,
            current_user=user,
            payload=update_credit_card_payload,
        )

        service.update.assert_awaited_once_with(
            param=credit_card_id,
            update_schema=update_credit_card_payload,
            user=user,
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_create_route_passes_authenticated_user_and_payload_to_service(
        user, create_credit_card_payload
    ):
        service = AsyncMock()

        await create(
            service=service,
            current_user=user,
            credit_card_data=create_credit_card_payload,
        )

        service.create.assert_awaited_once_with(
            user=user,
            payload=create_credit_card_payload,
        )
