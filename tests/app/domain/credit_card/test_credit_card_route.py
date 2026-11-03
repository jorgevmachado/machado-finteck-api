from unittest.mock import AsyncMock
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest

from app.core.database import get_session
from app.core.security import get_current_user
from app.domain.credit_card.route import (
    create,
    delete,
    find_one,
    list_all,
    credit_card_filter,
    credit_card_service,
    router,
    update,
)
from app.domain.credit_card.service import CreditCardService
from app.models import CreditCardBrandEnum
from app.shared.schemas import FilterPage, Message


def test_credit_card_service_builds_from_session():
    assert isinstance(credit_card_service(AsyncMock()), CreditCardService)


def test_credit_card_filter_builds_dynamic_filter():
    page_filter = credit_card_filter(page=1, name="Test Credit Card", limit=12)

    assert page_filter.page == 1
    assert page_filter.name == "Test Credit Card"
    assert page_filter.limit == 12


def test_credit_card_filter_passes_brand_and_active_and_drops_legacy_type():
    page_filter = credit_card_filter(
        page=1,
        name="Visa",
        brand=CreditCardBrandEnum.VISA,
        is_active=True,
        limit=5,
        offset=0,
    )

    assert page_filter.brand == CreditCardBrandEnum.VISA
    assert page_filter.is_active is True
    assert not hasattr(page_filter, "type")
    assert not hasattr(page_filter, "with_deleted")


class TestCreditCardRoutes:
    @staticmethod
    def test_create_endpoint_requires_authentication():
        app = FastAPI()
        app.include_router(router, prefix="/credit-cards")
        service = AsyncMock()
        app.dependency_overrides[credit_card_service] = lambda: service

        with TestClient(app) as client:
            response = client.post("/credit-cards", json={"name": "Test Credit Card"})

        assert response.status_code in (401, 403)
        service.create.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_crud_routes_delegate_with_authenticated_user(
        user, create_credit_card_payload, update_credit_card_payload
    ):
        resource_id = uuid4()
        service = AsyncMock()
        page_filter = FilterPage.build(name="Test Credit Card")

        await create(service, user, create_credit_card_payload)
        await list_all(service, user, page_filter)
        await find_one(resource_id, service, user)
        await update(service, resource_id, user, update_credit_card_payload)
        await delete(service, resource_id, user)

        service.create.assert_awaited_once_with(
            user=user, payload=create_credit_card_payload
        )
        service.list_all.assert_awaited_once_with(page_filter=page_filter, user=user)
        service.find_by.assert_awaited_once_with(filters={"id": resource_id}, user=user)
        service.update.assert_awaited_once_with(
            identifier=resource_id,
            payload=update_credit_card_payload,
            user=user,
        )
        service.delete.assert_awaited_once_with(user=user, identifier=resource_id)

    @staticmethod
    def test_delete_endpoint_preserves_service_response(user):
        app = FastAPI()
        app.include_router(router, prefix="/credit-cards")
        service = AsyncMock()
        service.delete.return_value = Message(message="Deleted")
        app.dependency_overrides[credit_card_service] = lambda: service
        app.dependency_overrides[get_current_user] = lambda: user
        credit_card_id = uuid4()

        with TestClient(app) as client:
            response = client.delete(f"/credit-cards/{credit_card_id}")
            malformed = client.delete("/credit-cards/not-a-uuid")

        assert response.status_code == 200
        assert response.json() == {"message": "Deleted"}
        assert malformed.status_code == 422


@pytest.mark.asyncio
async def test_http_crud_with_real_credit_card_service_and_database(
    credit_card_session, credit_card_cache, user
):
    app = FastAPI()
    app.include_router(router, prefix="/credit-cards")

    async def session_override():
        yield credit_card_session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_current_user] = lambda: user
    payload = {
        "name": "Test Credit Card",
        "brand": "VISA",
        "closing_day": 15,
        "due_day": 25,
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post("/credit-cards", json=payload)
        assert created.status_code == 201
        body = created.json()
        identifier = body["id"]
        assert body["name"] == "Test Credit Card"
        assert body["closing_day"] == 15
        assert (await client.get(f"/credit-cards/{identifier}")).json() == body
        page = await client.get(
            "/credit-cards",
            params={"offset": 0, "limit": 1, "name": "Test Credit Card"},
        )
        assert page.status_code == 200
        assert page.json()["meta"]["total"] == 1
        assert page.json()["items"] == [body]
        assert (await client.post("/credit-cards", json=payload)).status_code == 409
        updated = await client.put(
            f"/credit-cards/{identifier}", json={"color": "Blue"}
        )
        assert updated.json() == {
            "message": f"Update CreditCard {identifier} successfully"
        }
        assert (await client.get(f"/credit-cards/{identifier}")).json()[
            "color"
        ] == "Blue"
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=uuid4(), username="other"
        )
        for method in ("get", "put", "delete"):
            kwargs = {"json": {"color": "No"}} if method == "put" else {}
            assert (
                await getattr(client, method)(f"/credit-cards/{identifier}", **kwargs)
            ).status_code == 404
        assert (await client.get("/credit-cards")).json() == []
        app.dependency_overrides[get_current_user] = lambda: user
        deleted = await client.delete(f"/credit-cards/{identifier}")
        assert deleted.json() == {
            "message": f"Delete CreditCard {identifier} successfully"
        }
        assert (await client.get(f"/credit-cards/{identifier}")).status_code == 404
        assert (await client.delete(f"/credit-cards/{identifier}")).status_code == 404
