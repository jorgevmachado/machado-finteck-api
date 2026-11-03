from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.security import get_current_user
from app.domain.transaction.series.route import router, transaction_series_service
from app.domain.transaction.series.schema import (
    TransactionSeriesCreateSchema,
    TransactionSeriesSchema,
    TransactionSeriesUpdateSchema,
)
from app.domain.transaction.series.service import TransactionSeriesService


@pytest.fixture
def series_data():
    return {
        "kind": "CLOSED",
        "name": "Streaming subscription",
        "value": "39.90",
        "direction": "OUT",
        "account_id": str(uuid4()),
        "end_date": "2026-09-15",
        "frequency_unit": "MONTH",
        "frequency_interval": 1,
        "day_of_month": 10,
        "installments": 12,
    }


@pytest.mark.parametrize("include_null", [False, True])
def test_creation_requires_non_null_start_date(series_data, include_null):
    if include_null:
        series_data["start_date"] = None
    with pytest.raises(ValidationError) as caught:
        TransactionSeriesCreateSchema.model_validate(series_data)
    assert caught.value.errors()[0]["loc"] == ("start_date",)


def test_creation_preserves_start_date_in_entity(series_data, user):
    series_data["start_date"] = "2025-10-10"
    payload = TransactionSeriesCreateSchema.model_validate(series_data)
    entity = TransactionSeriesService(AsyncMock())._build_entity(
        user.id, payload.model_dump()
    )
    assert entity.start_date == date(2025, 10, 10)
    assert entity.user_id == user.id


def test_update_can_omit_or_replace_but_not_clear_start_date(series_data):
    payload = TransactionSeriesUpdateSchema.model_validate(series_data)
    assert "start_date" not in payload.model_dump(exclude_unset=True)
    updated = TransactionSeriesUpdateSchema.model_validate(
        series_data | {"start_date": "2025-10-10"}
    )
    assert updated.model_dump(exclude_unset=True)["start_date"] == date(2025, 10, 10)
    with pytest.raises(ValidationError) as caught:
        TransactionSeriesUpdateSchema.model_validate(series_data | {"start_date": None})
    assert caught.value.errors()[0]["loc"] == ("start_date",)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("kind", "INVALID"),
        ("frequency_unit", "DAY"),
        ("direction", "TRANSFER"),
        ("account_id", "not-a-uuid"),
        ("value", "not-money"),
        ("start_date", "not-a-date"),
    ],
)
def test_invalid_series_fields_are_rejected(series_payload, field, value):
    with pytest.raises(ValidationError) as caught:
        TransactionSeriesCreateSchema.model_validate(
            series_payload.model_dump() | {field: value}
        )
    assert caught.value.errors()[0]["loc"] == (field,)


def test_partial_update_preserves_explicit_null_and_omission():
    assert TransactionSeriesUpdateSchema().model_dump(exclude_unset=True) == {}
    payload = TransactionSeriesUpdateSchema(note=None, credit_card_id=None)
    assert payload.model_dump(exclude_unset=True) == {
        "note": None,
        "credit_card_id": None,
    }


def test_response_serializes_schedule_and_related_account(series_response):
    result = TransactionSeriesSchema.model_validate(series_response).model_dump(
        mode="json"
    )
    assert result["start_date"] == "2026-01-10"
    assert result["end_date"] == "2026-12-10"
    assert result["value"] == "39.90"
    assert result["account"]["id"] == series_response["account"]["id"]


@pytest.mark.parametrize("include_null", [False, True])
def test_http_rejects_missing_or_null_start_date_before_service(
    series_data, user, include_null
):
    if include_null:
        series_data["start_date"] = None
    app = FastAPI()
    app.include_router(router, prefix="/transactions/series")
    service = AsyncMock()
    app.dependency_overrides[transaction_series_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        response = client.post("/transactions/series", json=series_data)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "start_date"]
    service.create.assert_not_awaited()
