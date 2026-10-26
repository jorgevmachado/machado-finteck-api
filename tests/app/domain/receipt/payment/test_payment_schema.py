from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.receipt.payment.schema import PaymentSchema


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
