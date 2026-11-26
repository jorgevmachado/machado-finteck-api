from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.receipt.data.enums import DataStatusEnum
from app.domain.receipt.data.schema import ReceiptData
from app.domain.receipt.interpretation.converter import Converter
from app.domain.receipt.interpretation.schema import InterpretationResult
from app.domain.receipt.interpretation.validation import InterpretationValidator
from app.domain.receipt.schema import ReceiptConfirmSchema

COMPLETE_PAYLOAD: dict[str, object] = {
    "payer": "Payer",
    "beneficiary": "Beneficiary",
    "paid_amount": "123.45",
    "payment_date": "2026-10-26",
    "source_institution": "Source bank",
    "destination_institution": "Destination bank",
    "fine": "1.00",
    "barcode": "123456789",
    "due_date": "2026-10-20",
    "discount": "0.50",
    "interest": "0.25",
    "category": "Utilities",
    "description": "Monthly payment",
    "total_charges": "123.45",
    "authentication": "AUTH-1",
    "transaction_id": "TX-1",
    "effective_payer": "Effective payer",
    "document_amount": "123.45",
}


SCHEMA_PAYLOAD: dict[str, object] = {
    **COMPLETE_PAYLOAD,
    "name": "Netflix",
    "subcategory_id": str(uuid4()),
    "account_id": str(uuid4()),
}


def test_convert_data_marks_every_field_found_when_payload_is_complete():
    data = Converter(COMPLETE_PAYLOAD).data

    assert isinstance(data, ReceiptData)
    statuses = {name: getattr(data, name).status for name in ReceiptData.model_fields}
    assert set(statuses.values()) == {DataStatusEnum.FOUND}


def test_convert_data_preserves_typed_values_from_payload():
    data = Converter(COMPLETE_PAYLOAD).data

    assert data.paid_amount.value == Decimal("123.45")
    assert data.payment_date.value == date(2026, 10, 26)
    assert data.beneficiary.value == "Beneficiary"
    assert data.source_institution.value == "Source bank"


@pytest.mark.parametrize("field_name", list(ReceiptData.model_fields))
def test_convert_field_marks_not_found_when_key_is_absent(field_name):
    payload = {k: v for k, v in COMPLETE_PAYLOAD.items() if k != field_name}

    data = Converter(payload).data

    assert getattr(data, field_name).value is None
    assert getattr(data, field_name).status == DataStatusEnum.NOT_FOUND


@pytest.mark.parametrize("field_name", ["payer", "description", "barcode"])
def test_convert_field_treats_explicit_none_as_not_found(field_name):
    payload = {**COMPLETE_PAYLOAD, field_name: None}

    data = Converter(payload).data

    assert getattr(data, field_name).value is None
    assert getattr(data, field_name).status == DataStatusEnum.NOT_FOUND


@pytest.mark.parametrize(
    ("field_name", "value"),
    [("barcode", ""), ("paid_amount", Decimal("0"))],
)
def test_convert_field_treats_falsy_non_none_values_as_found(field_name, value):
    payload: dict[str, object] = {field_name: value}

    data = Converter(payload).data

    assert getattr(data, field_name).value == value
    assert getattr(data, field_name).status == DataStatusEnum.FOUND


def test_convert_data_marks_every_field_not_found_for_empty_payload():
    data = Converter({}).data

    assert all(
        getattr(data, name).status == DataStatusEnum.NOT_FOUND
        for name in ReceiptData.model_fields
    )


def test_result_returns_interpretation_without_errors_when_required_fields_present():
    result = Converter(COMPLETE_PAYLOAD).result()

    assert isinstance(result, InterpretationResult)
    assert result.errors == []
    assert result.data.payment_date.value == date(2026, 10, 26)


@pytest.mark.parametrize("missing", InterpretationValidator.REQUIRED_FIELDS)
def test_result_reports_each_missing_required_field_as_error(missing):
    payload = {k: v for k, v in COMPLETE_PAYLOAD.items() if k != missing}

    result = Converter(payload).result()

    assert [error.field for error in result.errors] == [missing]
    assert result.errors[0].status == DataStatusEnum.NOT_FOUND


def test_result_reports_all_missing_required_fields_in_validator_order():
    result = Converter({"payer": "Payer"}).result()

    assert [error.field for error in result.errors] == list(
        InterpretationValidator.REQUIRED_FIELDS
    )


def test_result_keeps_optional_fields_out_of_errors():
    payload: dict[str, object] = {
        "paid_amount": "10.00",
        "payment_date": "2026-10-26",
        "beneficiary": "Beneficiary",
        "source_institution": "Source bank",
    }

    result = Converter(payload).result()

    assert result.errors == []
    assert result.data.destination_institution.status == DataStatusEnum.NOT_FOUND


@pytest.mark.parametrize("field_name", ["payer", "beneficiary", "source_institution"])
def test_schema_rejects_blank_required_text_before_conversion(field_name):
    payload = {**SCHEMA_PAYLOAD, field_name: "   "}

    with pytest.raises(ValidationError, match="Field cannot be empty"):
        ReceiptConfirmSchema.model_validate(payload)


@pytest.mark.parametrize("field_name", ["payer", "beneficiary", "source_institution"])
def test_schema_strips_surrounding_whitespace_from_required_text(field_name):
    payload = {**SCHEMA_PAYLOAD, field_name: "  Valid value  "}

    schema = ReceiptConfirmSchema.model_validate(payload)

    assert getattr(schema, field_name) == "Valid value"


def test_schema_exposes_every_receipt_data_field():
    assert set(ReceiptData.model_fields) <= set(ReceiptConfirmSchema.model_fields)


def test_converter_marks_category_found_when_payload_carries_it():
    result = Converter({**COMPLETE_PAYLOAD, "category": "Utilities"}).result()

    assert result.data.category.value == "Utilities"
    assert result.data.category.status == DataStatusEnum.FOUND
    assert result.errors == []


@pytest.mark.parametrize("raw", ["0", "0.00"])
def test_converter_accepts_json_string_zero_for_decimal_field(raw):
    data = Converter({"paid_amount": raw}).data

    assert data.paid_amount.value == Decimal(raw)
    assert data.paid_amount.status == DataStatusEnum.FOUND
