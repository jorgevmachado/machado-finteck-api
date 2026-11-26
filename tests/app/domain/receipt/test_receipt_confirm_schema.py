from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.receipt.schema import ReceiptConfirmSchema, ReceiptUpdateSchema


@pytest.fixture
def confirm_payload():
    return {
        "name": "Netflix",
        "payer": "Payer",
        "beneficiary": "Beneficiary",
        "paid_amount": "123.45",
        "payment_date": "2026-11-10",
        "subcategory_id": str(uuid4()),
        "source_institution": "Source bank",
        "account_id": str(uuid4()),
    }


def test_simple_is_the_default_kind_and_requires_only_the_account(confirm_payload):
    payload = ReceiptConfirmSchema.model_validate(confirm_payload)

    assert payload.transaction_kind == "SIMPLE"
    assert payload.overwrite is False
    assert payload.direction == "OUT"
    assert payload.expected_on is None


def test_account_is_required_for_every_kind(confirm_payload):
    confirm_payload.pop("account_id")

    with pytest.raises(ValidationError) as caught:
        ReceiptConfirmSchema.model_validate(confirm_payload)

    assert caught.value.errors()[0]["loc"] == ("account_id",)


@pytest.mark.parametrize("field", ["installment_index", "installments_total"])
def test_simple_rejects_installment_fields(confirm_payload, field):
    with pytest.raises(ValidationError, match="SIMPLE does not accept"):
        ReceiptConfirmSchema.model_validate(confirm_payload | {field: 1})


@pytest.mark.parametrize("field", ["frequency_unit", "frequency_interval"])
def test_simple_rejects_recurrence_fields(confirm_payload, field):
    value = "MONTH" if field == "frequency_unit" else 1
    with pytest.raises(ValidationError, match="SIMPLE does not accept"):
        ReceiptConfirmSchema.model_validate(confirm_payload | {field: value})


@pytest.mark.parametrize("field", ["installment_index", "installments_total"])
def test_installment_requires_position_and_total(confirm_payload, field):
    values = {
        "installment_index": 3,
        "installments_total": 10,
        "transaction_kind": "INSTALLMENT",
    }
    values.pop(field)

    with pytest.raises(ValidationError, match="are required for INSTALLMENT"):
        ReceiptConfirmSchema.model_validate(confirm_payload | values)


def test_installment_rejects_recurrence_fields(confirm_payload):
    with pytest.raises(ValidationError, match="not allowed for INSTALLMENT"):
        ReceiptConfirmSchema.model_validate(
            confirm_payload
            | {
                "transaction_kind": "INSTALLMENT",
                "installment_index": 3,
                "installments_total": 10,
                "frequency_unit": "MONTH",
            }
        )


@pytest.mark.parametrize("index", [0, -1])
def test_installment_rejects_position_below_one(confirm_payload, index):
    with pytest.raises(ValidationError, match="installment_index must be at least 1"):
        ReceiptConfirmSchema.model_validate(
            confirm_payload
            | {
                "transaction_kind": "INSTALLMENT",
                "installment_index": index,
                "installments_total": 10,
            }
        )


def test_installment_rejects_total_smaller_than_position(confirm_payload):
    with pytest.raises(ValidationError, match="must be greater than or equal"):
        ReceiptConfirmSchema.model_validate(
            confirm_payload
            | {
                "transaction_kind": "INSTALLMENT",
                "installment_index": 5,
                "installments_total": 4,
            }
        )


def test_installment_accepts_position_equal_to_total(confirm_payload):
    payload = ReceiptConfirmSchema.model_validate(
        confirm_payload
        | {
            "transaction_kind": "INSTALLMENT",
            "installment_index": 4,
            "installments_total": 4,
        }
    )

    assert (payload.installment_index, payload.installments_total) == (4, 4)


@pytest.mark.parametrize("field", ["frequency_unit", "frequency_interval"])
def test_recurring_requires_frequency_fields(confirm_payload, field):
    values = {
        "transaction_kind": "RECURRING",
        "frequency_unit": "MONTH",
        "frequency_interval": 1,
    }
    values.pop(field)

    with pytest.raises(ValidationError, match="are required for RECURRING"):
        ReceiptConfirmSchema.model_validate(confirm_payload | values)


def test_recurring_rejects_installment_fields(confirm_payload):
    with pytest.raises(ValidationError, match="not allowed for RECURRING"):
        ReceiptConfirmSchema.model_validate(
            confirm_payload
            | {
                "transaction_kind": "RECURRING",
                "frequency_unit": "MONTH",
                "frequency_interval": 1,
                "installment_index": 1,
            }
        )


@pytest.mark.parametrize("interval", [0, -2])
def test_recurring_rejects_non_positive_interval(confirm_payload, interval):
    with pytest.raises(ValidationError, match="frequency_interval must be at least 1"):
        ReceiptConfirmSchema.model_validate(
            confirm_payload
            | {
                "transaction_kind": "RECURRING",
                "frequency_unit": "MONTH",
                "frequency_interval": interval,
            }
        )


def test_unknown_kind_is_rejected(confirm_payload):
    with pytest.raises(ValidationError) as caught:
        ReceiptConfirmSchema.model_validate(
            confirm_payload | {"transaction_kind": "TRANSFER"}
        )

    assert caught.value.errors()[0]["loc"] == ("transaction_kind",)


def test_update_payload_stays_free_of_confirmation_fields():
    payload = ReceiptUpdateSchema.model_validate(
        {
            "payer": "Payer",
            "beneficiary": "Beneficiary",
            "paid_amount": "123.45",
            "payment_date": "2026-11-10",
            "subcategory_id": str(uuid4()),
            "source_institution": "Source bank",
        }
    )

    assert "account_id" not in ReceiptUpdateSchema.model_fields
    assert "transaction_kind" not in ReceiptUpdateSchema.model_fields
    assert payload.payment_date == date(2026, 11, 10)
