import pytest
from pydantic import ValidationError

from app.domain.credit_card.schema import CreditCardCreateSchema, CreditCardUpdateSchema
from app.models import CreditCardBrandEnum


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"color": "Blue"},
        {"name": "New name"},
        {"due_day": 15},
        {"closing_day": 10},
        {"brand": CreditCardBrandEnum.VISA},
    ],
)
def test_update_accepts_omitted_name_and_type(payload):
    schema = CreditCardUpdateSchema.model_validate(payload)

    assert schema.model_dump(exclude_unset=True) == payload


@pytest.mark.parametrize("field", ["name", "brand"])
def test_update_rejects_explicit_null_for_non_nullable_fields(field):
    with pytest.raises(ValidationError):
        CreditCardUpdateSchema.model_validate({field: None})


@pytest.mark.parametrize(
    "payload",
    [{}, {"name": "New name"}, {"brand": CreditCardBrandEnum.VISA}],
)
def test_create_still_requires_name_and_type(payload):
    with pytest.raises(ValidationError):
        CreditCardCreateSchema.model_validate(payload)
