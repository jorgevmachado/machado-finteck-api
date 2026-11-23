from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.domain.transaction.scheduled.schema import (
    ScheduledTransactionCreateSchema,
    ScheduledTransactionRequestCreateSchema,
    ScheduledTransactionSchema,
    ScheduledTransactionUpdateSchema,
)
from app.models import TransactionDirectionEnum, TransactionStatusEnum


def test_create_parses_dates_identifiers_and_defaults(scheduled_data):
    payload = ScheduledTransactionRequestCreateSchema.model_validate(scheduled_data)
    assert payload.value == Decimal("125.90")
    assert payload.direction == TransactionDirectionEnum.OUT
    assert payload.status == TransactionStatusEnum.PENDING
    assert payload.account_id == UUID(scheduled_data["account_id"])
    assert payload.expected_on == date(2026, 11, 10)
    assert payload.occurrence_on == date(2026, 11, 10)
    assert payload.occurrence_index == 1


def test_create_requires_series_id_and_uses_model_field_name(scheduled_data):
    with pytest.raises(ValidationError) as caught:
        ScheduledTransactionCreateSchema.model_validate(scheduled_data)
    assert caught.value.errors()[0]["loc"] == ("transaction_series_id",)

    series_id = uuid4()
    payload = ScheduledTransactionCreateSchema.model_validate(
        scheduled_data | {"transaction_series_id": str(series_id)}
    )
    assert payload.transaction_series_id == series_id


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("direction", "TRANSFER"),
        ("status", "UNKNOWN"),
        ("value", "not-money"),
        ("account_id", "not-a-uuid"),
        ("expected_on", "not-a-date"),
        ("occurrence_on", "not-a-date"),
        ("occurrence_index", "not-an-integer"),
    ],
)
def test_create_rejects_malformed_fields(scheduled_data, field, value):
    with pytest.raises(ValidationError) as caught:
        ScheduledTransactionRequestCreateSchema.model_validate(
            scheduled_data | {field: value}
        )
    assert caught.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize(
    "field",
    [
        "name",
        "value",
        "direction",
        "account_id",
        "expected_on",
        "occurrence_on",
        "occurrence_index",
    ],
)
def test_create_requires_mandatory_fields(scheduled_data, field):
    scheduled_data.pop(field)
    with pytest.raises(ValidationError) as caught:
        ScheduledTransactionRequestCreateSchema.model_validate(scheduled_data)
    assert caught.value.errors()[0]["loc"] == (field,)


def test_partial_update_preserves_omission_and_explicit_null():
    assert ScheduledTransactionUpdateSchema().model_dump(exclude_unset=True) == {}
    payload = ScheduledTransactionUpdateSchema(note=None, credit_card_id=None)
    assert payload.model_dump(exclude_unset=True) == {
        "note": None,
        "credit_card_id": None,
    }


def test_update_can_set_series_id_for_route_scope():
    series_id = uuid4()
    payload = ScheduledTransactionUpdateSchema(note="Changed").model_copy(
        update={"transaction_series_id": series_id}
    )
    assert payload.model_dump(exclude_unset=True) == {
        "note": "Changed",
        "transaction_series_id": series_id,
    }


def test_response_serializes_nested_relations_and_money(scheduled_response):
    result = ScheduledTransactionSchema.model_validate(scheduled_response).model_dump(
        mode="json"
    )
    assert result["value"] == "125.90"
    assert result["account"]["id"] == scheduled_response["account"]["id"]
    assert (
        result["transaction_serie"]["id"]
        == scheduled_response["transaction_serie"]["id"]
    )
