from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.domain.transaction.route import (
    create,
    delete,
    find_one,
    list_all,
    router,
    transaction_filter,
    transaction_service,
    update,
)
from app.domain.transaction.schema import (
    TransactionUpdateSchema,
    TransactionSeedRequestSchema,
)
from app.domain.transaction.service import TransactionService
from app.models import TransactionDirectionEnum, TransactionStatusEnum
from app.shared.schemas import Message


@pytest.fixture
def route_service():
    return AsyncMock()


@pytest.fixture
def transaction_client(route_service, user):
    app = FastAPI()
    app.include_router(router, prefix="/transactions")
    app.dependency_overrides[transaction_service] = lambda: route_service
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        yield client


def test_factory_builds_service(transaction_session):
    service = transaction_service(transaction_session)
    assert isinstance(service, TransactionService)
    assert service.repository.session is transaction_session


def test_filter_preserves_transaction_criteria():
    filters = transaction_filter(
        page=2,
        name="Payment",
        status=TransactionStatusEnum.SETTLED,
        direction=TransactionDirectionEnum.OUT,
        limit=5,
        offset=0,
        clean_cache=True,
    )
    assert filters.model_dump(exclude_none=True) == {
        "page": 2,
        "name": "Payment",
        "status": TransactionStatusEnum.SETTLED,
        "direction": TransactionDirectionEnum.OUT,
        "limit": 5,
        "offset": 0,
        "clean_cache": True,
    }


@pytest.mark.asyncio
async def test_crud_delegates_with_authenticated_owner(
    route_service, transaction_payload, user
):
    identifier = uuid4()
    filters = transaction_filter()
    payload = TransactionUpdateSchema(note="Updated")
    await create(route_service, user, transaction_payload)
    await list_all(route_service, user, filters)
    await find_one(identifier, route_service, user)
    await update(route_service, identifier, user, payload)
    await delete(route_service, identifier, user)
    route_service.create.assert_awaited_once_with(
        user=user, payload=transaction_payload
    )
    route_service.list_all.assert_awaited_once_with(page_filter=filters, user=user)
    route_service.find_by.assert_awaited_once_with(
        filters={"id": identifier}, user=user
    )
    route_service.update.assert_awaited_once_with(
        identifier=identifier, payload=payload, user=user
    )
    route_service.delete.assert_awaited_once_with(user=user, identifier=identifier)


def test_http_create_and_list_serialize_response(
    transaction_client, route_service, transaction_data, transaction_response
):
    route_service.create.return_value = transaction_response
    route_service.list_all.return_value = [transaction_response]
    created = transaction_client.post("/transactions", json=transaction_data)
    assert created.status_code == 201
    assert created.json()["value"] == "125.90"
    assert created.json()["account"]["id"] == transaction_data["account_id"]
    listed = transaction_client.get("/transactions", params={"status": "PENDING"})
    assert listed.status_code == 200
    assert listed.json() == [created.json()]
    assert (
        route_service.list_all.await_args.kwargs["page_filter"].status
        == TransactionStatusEnum.PENDING
    )


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/transactions", {"name": "Incomplete"}),
        ("get", "/transactions/not-a-uuid", None),
        ("get", "/transactions?status=INVALID", None),
        ("put", "/transactions/not-a-uuid", {"note": "No"}),
    ],
)
def test_http_rejects_invalid_input(
    transaction_client, route_service, method, path, body
):
    kwargs = {"json": body} if body is not None else {}
    response = getattr(transaction_client, method)(path, **kwargs)
    assert response.status_code == 422
    for operation in ("create", "list_all", "find_by", "update"):
        getattr(route_service, operation).assert_not_awaited()


def test_http_preserves_not_found_and_mutation_messages(
    transaction_client, route_service
):
    identifier = uuid4()
    route_service.find_by.side_effect = HTTPException(404, "Transaction not found")
    route_service.update.return_value = Message(message="Updated")
    route_service.delete.return_value = Message(message="Deleted")
    missing = transaction_client.get(f"/transactions/{identifier}")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Transaction not found"}
    assert transaction_client.put(
        f"/transactions/{identifier}", json={"note": "Updated"}
    ).json() == {"message": "Updated"}
    assert transaction_client.delete(f"/transactions/{identifier}").json() == {
        "message": "Deleted"
    }


@pytest.mark.parametrize("method", ["get", "post", "put", "delete"])
def test_http_requires_authentication(method, transaction_data):
    app = FastAPI()
    app.include_router(router, prefix="/transactions")
    service = AsyncMock()
    app.dependency_overrides[transaction_service] = lambda: service
    path = "/transactions" if method in ("get", "post") else f"/transactions/{uuid4()}"
    kwargs = {"json": transaction_data} if method in ("post", "put") else {}
    with TestClient(app) as client:
        response = getattr(client, method)(path, **kwargs)
    assert response.status_code in (401, 403)
    for operation in ("create", "list_all", "find_by", "update", "delete"):
        getattr(service, operation).assert_not_awaited()


def test_seed_http_delegates_validated_request(transaction_client, route_service, user):
    user.role = SimpleNamespace(name_code="admin", deleted_at=None)
    route_service.seed.return_value = {
        "seed": 42,
        "start_date": "2026-06-01",
        "end_date": "2026-11-30",
        "transactions": 100,
        "transaction_series": 10,
        "scheduled_transactions": 50,
    }
    response = transaction_client.post("/transactions/seed", json={"seed": 42})
    assert response.status_code == 201
    assert response.json()["scheduled_transactions"] == 50
    route_service.seed.assert_awaited_once_with(
        user=user, payload=TransactionSeedRequestSchema(seed=42)
    )


@pytest.mark.parametrize("role", [None, "user", "ADMIN", "deleted-admin"])
def test_seed_http_denies_non_admin_before_database_access(
    transaction_client,
    route_service,
    transaction_service,
    transaction_repository,
    user,
    role,
):
    user.role = (
        SimpleNamespace(
            name_code="admin" if role == "deleted-admin" else role,
            deleted_at=date(2026, 1, 1) if role == "deleted-admin" else None,
        )
        if role
        else None
    )
    route_service.seed.side_effect = transaction_service.seed
    response = transaction_client.post("/transactions/seed", json={})
    assert response.status_code == 403
    transaction_repository.transaction.assert_not_called()


def test_seed_http_requires_authentication():
    app = FastAPI()
    app.include_router(router, prefix="/transactions")
    service = AsyncMock()
    app.dependency_overrides[transaction_service] = lambda: service
    with TestClient(app) as client:
        response = client.post("/transactions/seed", json={})
    assert response.status_code == 401
    service.seed.assert_not_awaited()


def test_seed_http_rejects_invalid_input(transaction_client, route_service):
    response = transaction_client.post(
        "/transactions/seed", json={"transactions": 1001}
    )
    assert response.status_code == 422
    route_service.seed.assert_not_awaited()
