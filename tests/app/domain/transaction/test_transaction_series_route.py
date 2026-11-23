from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.transaction.route import router as transaction_router
from app.domain.transaction.series.route import (
    router,
    transaction_series_filter,
    transaction_series_service,
)
from app.domain.transaction.series.schema import TransactionSeriesSchema
from app.domain.transaction.series.service import TransactionSeriesService
from app.shared.schemas import Message
from fastapi_pagination import LimitOffsetParams


@pytest.fixture
def series_route_service():
    return AsyncMock()


@pytest.fixture
def series_client(series_route_service, user):
    app = FastAPI()
    app.include_router(transaction_router, prefix="/transactions")
    app.dependency_overrides[transaction_series_service] = lambda: series_route_service
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        yield client


def test_factory_and_filter(transaction_session):
    service = transaction_series_service(transaction_session)
    assert isinstance(service, TransactionSeriesService)
    assert service.repository.session is transaction_session
    filters = transaction_series_filter(
        page=2,
        name="Subscription",
        kind="CLOSED",
        direction="OUT",
        frequency_unit="MONTH",
        limit=5,
        offset=0,
        clean_cache=True,
    )
    assert filters.model_dump(exclude_none=True) == {
        "page": 2,
        "name": "Subscription",
        "kind": "CLOSED",
        "direction": "OUT",
        "frequency_unit": "MONTH",
        "limit": 5,
        "offset": 0,
        "clean_cache": True,
    }


def test_http_crud_delegates_and_preserves_contract(
    series_client, series_route_service, series_payload, series_response, user
):
    identifier = series_response["id"]
    service = series_route_service
    service.create.return_value = series_response
    service.find_by.return_value = series_response
    service.list_all.return_value = [series_response]
    service.update.return_value = Message(message="Updated")
    service.delete.return_value = Message(message="Deleted")
    created = series_client.post(
        "/transactions/series", json=series_payload.model_dump(mode="json")
    )
    assert created.status_code == 201
    assert created.json()["value"] == "39.90"
    service.create.assert_awaited_once_with(user=user, payload=series_payload)
    found = series_client.get(f"/transactions/series/{identifier}")
    assert found.status_code == 200
    assert found.json() == created.json()
    service.find_by.assert_awaited_once_with(
        filters={"id": UUID(identifier)}, user=user
    )


def test_http_list_and_mutations(
    series_client, series_route_service, series_response, user
):
    identifier = UUID(series_response["id"])
    service = series_route_service
    service.list_all.return_value = [series_response]
    service.update.return_value = Message(message="Updated")
    service.delete.return_value = Message(message="Deleted")
    listed = series_client.get(
        "/transactions/series", params={"kind": "CLOSED", "frequency_unit": "MONTH"}
    )
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == str(identifier)
    filters = service.list_all.await_args.kwargs["page_filter"]
    assert filters.kind == "CLOSED"
    assert filters.frequency_unit == "MONTH"
    assert service.list_all.await_args.kwargs["user"] is user
    updated = series_client.put(
        f"/transactions/series/{identifier}", json={"note": "Changed"}
    )
    assert updated.status_code == 200
    assert updated.json() == {"message": "Updated"}
    call = service.update.await_args.kwargs
    assert call["identifier"] == identifier
    assert call["user"] is user
    assert call["payload"].model_dump(exclude_unset=True) == {"note": "Changed"}
    deleted = series_client.delete(f"/transactions/series/{identifier}")
    assert deleted.status_code == 200
    assert deleted.json() == {"message": "Deleted"}
    service.delete.assert_awaited_once_with(user=user, identifier=identifier)


def test_http_paginated_response(series_client, series_route_service, series_response):
    series_route_service.list_all.return_value = CustomLimitOffsetPage.create(
        [TransactionSeriesSchema.model_validate(series_response)],
        params=LimitOffsetParams(limit=1, offset=0),
        total=3,
    )
    response = series_client.get("/transactions/series?limit=1&offset=0")
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 3
    assert response.json()["items"][0]["id"] == series_response["id"]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/transactions/series/not-a-uuid", None),
        ("get", "/transactions/series?frequency_unit=DAY", None),
        ("put", "/transactions/series/not-a-uuid", {"note": "No"}),
        ("post", "/transactions/series", {"kind": "INVALID"}),
    ],
)
def test_invalid_input_never_calls_service(
    series_client, series_route_service, method, path, body
):
    kwargs = {"json": body} if body is not None else {}
    assert getattr(series_client, method)(path, **kwargs).status_code == 422
    for operation in ("create", "list_all", "find_by", "update"):
        getattr(series_route_service, operation).assert_not_awaited()


def test_not_found_is_preserved(series_client, series_route_service):
    series_route_service.find_by.side_effect = HTTPException(404, "Series not found")
    response = series_client.get(f"/transactions/series/{uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Series not found"}


@pytest.mark.parametrize("method", ["get", "post", "put", "delete"])
def test_authentication_required(method, series_payload):
    app = FastAPI()
    app.include_router(router, prefix="/transactions/series")
    service = AsyncMock()
    app.dependency_overrides[transaction_series_service] = lambda: service
    path = "/transactions/series"
    if method in ("put", "delete"):
        path += f"/{uuid4()}"
    kwargs = (
        {"json": series_payload.model_dump(mode="json")}
        if method in ("post", "put")
        else {}
    )
    with TestClient(app) as client:
        assert getattr(client, method)(path, **kwargs).status_code in (401, 403)
    for operation in ("create", "list_all", "find_by", "update", "delete"):
        getattr(service, operation).assert_not_awaited()
