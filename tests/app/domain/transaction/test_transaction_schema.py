from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.domain.transaction.schema import (
    TransactionCreateSchema,
    TransactionSchema,
    TransactionUpdateSchema,
)
from app.models import TransactionDirectionEnum, TransactionStatusEnum


def test_create_parses_money_dates_identifiers_and_defaults(transaction_data):
    payload = TransactionCreateSchema.model_validate(transaction_data)
    assert payload.value == Decimal("125.90")
    assert payload.direction == TransactionDirectionEnum.OUT
    assert payload.status == TransactionStatusEnum.PENDING
    assert payload.account_id == UUID(transaction_data["account_id"])
    assert payload.expected_on == date(2026, 11, 10)
    assert payload.settled_on is None
    assert payload.credit_card_id is None
    assert payload.subcategory_id is None


def test_create_accepts_settled_income_and_optional_relations(transaction_data):
    card_id, subcategory_id = uuid4(), uuid4()
    payload = TransactionCreateSchema.model_validate(
        transaction_data
        | {
            "direction": "IN",
            "status": "SETTLED",
            "settled_on": "2026-11-09",
            "credit_card_id": str(card_id),
            "subcategory_id": str(subcategory_id),
            "note": "Received",
        }
    )
    assert payload.direction == TransactionDirectionEnum.IN
    assert payload.status == TransactionStatusEnum.SETTLED
    assert payload.settled_on == date(2026, 11, 9)
    assert payload.credit_card_id == card_id
    assert payload.subcategory_id == subcategory_id
    assert payload.note == "Received"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("direction", "TRANSFER"),
        ("status", "UNKNOWN"),
        ("value", "not-money"),
        ("account_id", "not-a-uuid"),
        ("expected_on", "not-a-date"),
    ],
)
def test_create_rejects_malformed_fields(transaction_data, field, value):
    with pytest.raises(ValidationError) as caught:
        TransactionCreateSchema.model_validate(transaction_data | {field: value})
    assert caught.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize(
    "field", ["name", "value", "direction", "account_id", "expected_on"]
)
def test_create_requires_mandatory_fields(transaction_data, field):
    transaction_data.pop(field)
    with pytest.raises(ValidationError) as caught:
        TransactionCreateSchema.model_validate(transaction_data)
    assert caught.value.errors()[0]["loc"] == (field,)


def test_partial_update_preserves_omission_and_explicit_null():
    assert TransactionUpdateSchema().model_dump(exclude_unset=True) == {}
    payload = TransactionUpdateSchema(note=None, credit_card_id=None, value="90.15")
    assert payload.model_dump(exclude_unset=True) == {
        "note": None,
        "credit_card_id": None,
        "value": Decimal("90.15"),
    }


def test_response_serializes_nested_account_and_money(transaction_response):
    response = TransactionSchema.model_validate(transaction_response)
    serialized = response.model_dump(mode="json")
    assert serialized["value"] == "125.90"
    assert serialized["account"]["id"] == transaction_response["account"]["id"]
    assert serialized["credit_card"] is None
    assert serialized["subcategory"] is None
