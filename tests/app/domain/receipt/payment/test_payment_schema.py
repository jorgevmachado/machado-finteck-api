from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.receipt.payment.schema import (
    PaymentSchema,
    PaymentDashboardRequestSchema,
    PaymentDashboardResponseSchema,
)


@pytest.mark.parametrize("with_optional_fields", [False, True])
def test_schema_reads_nested_attributes_and_serializes_payment(
    payment_output, with_optional_fields
):
    if not with_optional_fields:
        del payment_output.description
        del payment_output.destination_institution

    result = PaymentSchema.model_validate(payment_output)
    serialized = result.model_dump(mode="json")

    assert result.amount == Decimal("123.45")
    assert serialized["amount"] == "123.45"
    assert serialized["payment_date"] == payment_output.payment_date.isoformat()
    assert serialized["payer"]["id"] == str(payment_output.payer.id)
    assert serialized["receipt"]["id"] == str(payment_output.receipt.id)
    assert serialized["subcategory"]["id"] == str(payment_output.subcategory.id)
    assert serialized["beneficiary"]["id"] == str(payment_output.beneficiary.id)
    assert serialized["source_institution"]["id"] == str(
        payment_output.source_institution.id
    )
    if with_optional_fields:
        assert serialized["description"] == payment_output.description
        assert serialized["destination_institution"]["id"] == str(
            payment_output.destination_institution.id
        )
    else:
        assert result.description is None
        assert result.destination_institution is None


@pytest.mark.parametrize(
    ("field", "value"),
    [("payer", None), ("amount", "invalid"), ("payment_date", "invalid")],
)
def test_schema_rejects_incomplete_or_invalid_payment(payment_output, field, value):
    setattr(payment_output, field, value)

    with pytest.raises(ValidationError) as caught:
        PaymentSchema.model_validate(payment_output)

    assert caught.value.errors()[0]["loc"][0] == field


def test_dashboard_response_serializes_nested_identifiers_money_and_dates(
    dashboard_response, dashboard_params
):
    result = PaymentDashboardResponseSchema.model_validate(dashboard_response)
    serialized = result.model_dump(mode="json")

    assert serialized["period"] == {
        "start_date": dashboard_params.start_date.isoformat(),
        "end_date": dashboard_params.end_date.isoformat(),
    }
    assert serialized["summary"]["total"] == "123.45"
    for group, identifier in (
        ("subcategories", "subcategory_id"),
        ("payers", "payer_id"),
        ("beneficiaries", "beneficiary_id"),
    ):
        assert serialized[group][0][identifier] == str(
            dashboard_response[group][0][identifier]
        )
        assert serialized[group][0]["total"] == "123.45"
    assert serialized["monthly"][0]["period"] == "2026-10"
    assert serialized["institutions"][0]["institution"] == "source_bank"


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("summary", "total", "invalid"),
        ("subcategories", "subcategory_id", "invalid"),
        ("beneficiaries", "beneficiary_id", "invalid"),
        ("payers", "payer_id", "invalid"),
    ],
)
def test_dashboard_response_rejects_invalid_nested_data(
    dashboard_response, section, field, value
):
    target = dashboard_response[section]
    if isinstance(target, list):
        target = target[0]
    target[field] = value

    with pytest.raises(ValidationError) as caught:
        PaymentDashboardResponseSchema.model_validate(dashboard_response)

    assert caught.value.errors()[0]["loc"][0] == section


def test_dashboard_request_parses_filters_and_defaults(dashboard_params):
    result = PaymentDashboardRequestSchema.model_validate(
        dashboard_params.model_dump(mode="json")
    )
    assert result == dashboard_params
    unfiltered = PaymentDashboardRequestSchema(
        start_date="2026-01-01", end_date="2026-12-31"
    )
    assert unfiltered.institution is None
    assert unfiltered.payer_id is None
    assert unfiltered.subcategory_id is None
    assert unfiltered.beneficiary_id is None
