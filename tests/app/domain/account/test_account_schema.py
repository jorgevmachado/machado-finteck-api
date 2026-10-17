import pytest
from pydantic import ValidationError

from app.domain.account.schema import AccountCreateSchema, AccountUpdateSchema
from app.models import AccountTypeEnum


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"color": "Blue"},
        {"name": "New name"},
        {"type": AccountTypeEnum.SAVINGS},
    ],
)
def test_update_accepts_omitted_name_and_type(payload):
    schema = AccountUpdateSchema.model_validate(payload)

    assert schema.model_dump(exclude_unset=True) == payload


@pytest.mark.parametrize("field", ["name", "type"])
def test_update_rejects_explicit_null_for_non_nullable_fields(field):
    with pytest.raises(ValidationError):
        AccountUpdateSchema.model_validate({field: None})


@pytest.mark.parametrize(
    "payload",
    [{}, {"name": "New name"}, {"type": AccountTypeEnum.CASH}],
)
def test_create_still_requires_name_and_type(payload):
    with pytest.raises(ValidationError):
        AccountCreateSchema.model_validate(payload)
