from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from fastapi_pagination import LimitOffsetParams

from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.transaction.scheduled.route import (
    router,
    scheduled_transaction_filter,
    scheduled_transaction_service,
)
from app.domain.transaction.scheduled.schema import (
    ScheduledTransactionCreateSchema,
    ScheduledTransactionRequestUpdateSchema,
    ScheduledTransactionSchema,
)
from app.domain.transaction.scheduled.service import ScheduledTransactionService
from app.models import TransactionDirectionEnum, TransactionStatusEnum
from app.shared.schemas import Message


@pytest.fixture
def scheduled_route_service():
    return AsyncMock()


@pytest.fixture
def scheduled_client(scheduled_route_service, user):
    app = FastAPI()
    app.include_router(router, prefix="/transactions/scheduled")
    app.dependency_overrides[scheduled_transaction_service] = (
        lambda: scheduled_route_service
    )
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_factory_and_filter(transaction_session):
    service = scheduled_transaction_service(transaction_session)
    assert isinstance(service, ScheduledTransactionService)
    assert service.repository.session is transaction_session

    series_id = uuid4()
    filters = scheduled_transaction_filter(
        page=2,
        name="Payment",
        status=TransactionStatusEnum.SETTLED,
        direction=TransactionDirectionEnum.OUT,
        limit=5,
        offset=0,
        clean_cache=True,
        transaction_series_id=series_id,
    )
    assert filters.model_dump(exclude_none=True) == {
        "page": 2,
        "name": "Payment",
        "status": TransactionStatusEnum.SETTLED,
        "direction": TransactionDirectionEnum.OUT,
        "limit": 5,
        "offset": 0,
        "clean_cache": True,
        "transaction_series_id": series_id,
    }


def test_http_crud_scopes_transactions_to_series(
    scheduled_client, scheduled_route_service, scheduled_data, scheduled_response, user
):
    series_id = uuid4()
    scheduled_id = UUID(scheduled_response["id"])
    service = scheduled_route_service
    service.create.return_value = scheduled_response
    service.find_by.return_value = scheduled_response
    service.list_all.return_value = [scheduled_response]
    service.update_scheduled.return_value = Message(message="Updated")
    service.delete_scheduled.return_value = Message(message="Deleted")

    created = scheduled_client.post(
        f"/transactions/scheduled/{series_id}", json=scheduled_data
    )
    assert created.status_code == 201
    assert created.json()["value"] == "125.90"
    service.create.assert_awaited_once_with(
        user=user,
        payload=ScheduledTransactionCreateSchema.model_validate(
            scheduled_data | {"transaction_series_id": series_id}
        ),
    )

    listed = scheduled_client.get(
        f"/transactions/scheduled/{series_id}",
        params={"status": "PENDING", "direction": "OUT"},
    )
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == str(scheduled_id)
    page_filter = service.list_all.await_args.kwargs["page_filter"]
    assert page_filter.transaction_series_id == series_id
    assert page_filter.status == TransactionStatusEnum.PENDING
    assert service.list_all.await_args.kwargs["user"] is user

    found = scheduled_client.get(
        f"/transactions/scheduled/{series_id}/{scheduled_id}"
    )
    assert found.status_code == 200
    service.find_by.assert_awaited_once_with(
        filters={"id": scheduled_id, "transaction_series_id": series_id}, user=user
    )

    updated = scheduled_client.put(
        f"/transactions/scheduled/{series_id}/{scheduled_id}",
        json={"note": "Changed"},
    )
    assert updated.status_code == 200
    assert updated.json() == {"message": "Updated"}
    service.update_scheduled.assert_awaited_once_with(
        identifier=scheduled_id,
        transaction_series_id=series_id,
        payload=ScheduledTransactionRequestUpdateSchema(note="Changed"),
        user=user,
    )
    assert service.update_scheduled.await_args.kwargs["payload"].model_dump(
        exclude_unset=True
    ) == {"note": "Changed"}
    service.update.assert_not_awaited()

    deleted = scheduled_client.delete(
        f"/transactions/scheduled/{series_id}/{scheduled_id}"
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"message": "Deleted"}
    service.delete_scheduled.assert_awaited_once_with(
        user=user, identifier=scheduled_id, transaction_series_id=series_id
    )


def test_http_paginated_response(
    scheduled_client, scheduled_route_service, scheduled_response
):
    scheduled_route_service.list_all.return_value = CustomLimitOffsetPage.create(
        [ScheduledTransactionSchema.model_validate(scheduled_response)],
        params=LimitOffsetParams(limit=1, offset=0),
        total=3,
    )
    response = scheduled_client.get(
        f"/transactions/scheduled/{uuid4()}?limit=1&offset=0"
    )
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 3
    assert response.json()["items"][0]["id"] == scheduled_response["id"]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/transactions/scheduled/not-a-uuid", None),
        ("get", f"/transactions/scheduled/{uuid4()}?status=INVALID", None),
        ("get", f"/transactions/scheduled/{uuid4()}/not-a-uuid", None),
        ("post", f"/transactions/scheduled/{uuid4()}", {"name": "Incomplete"}),
        (
            "put",
            f"/transactions/scheduled/{uuid4()}/not-a-uuid",
            {"note": "No"},
        ),
    ],
)
def test_invalid_input_never_calls_service(
    scheduled_client, scheduled_route_service, method, path, body
):
    kwargs = {"json": body} if body is not None else {}
    assert getattr(scheduled_client, method)(path, **kwargs).status_code == 422
    for operation in (
        "create", "list_all", "find_by", "update", "update_scheduled", "delete_scheduled"
    ):
        getattr(scheduled_route_service, operation).assert_not_awaited()


def test_not_found_is_preserved(scheduled_client, scheduled_route_service):
    scheduled_route_service.find_by.side_effect = HTTPException(
        404, "ScheduledTransaction not found"
    )
    response = scheduled_client.get(
        f"/transactions/scheduled/{uuid4()}/{uuid4()}"
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "ScheduledTransaction not found"}


def test_update_preserves_not_found_for_other_series(
    scheduled_client, scheduled_route_service
):
    scheduled_route_service.update_scheduled.side_effect = HTTPException(
        404, "ScheduledTransaction not found"
    )
    response = scheduled_client.put(
        f"/transactions/scheduled/{uuid4()}/{uuid4()}",
        json={"note": "Changed"},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "ScheduledTransaction not found"}
    scheduled_route_service.update.assert_not_awaited()


@pytest.mark.parametrize("method", ["get", "post", "put", "delete"])
def test_authentication_required(method, scheduled_data):
    app = FastAPI()
    app.include_router(router, prefix="/transactions/scheduled")
    service = AsyncMock()
    app.dependency_overrides[scheduled_transaction_service] = lambda: service
    series_id = uuid4()
    path = f"/transactions/scheduled/{series_id}"
    if method in ("put", "delete"):
        path += f"/{uuid4()}"
    kwargs = {"json": scheduled_data} if method in ("post", "put") else {}
    with TestClient(app) as client:
        assert getattr(client, method)(path, **kwargs).status_code in (401, 403)
    for operation in (
        "create", "list_all", "find_by", "update", "update_scheduled", "delete_scheduled"
    ):
        getattr(service, operation).assert_not_awaited()
