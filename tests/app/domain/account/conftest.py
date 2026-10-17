from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.domain.account.schema import AccountCreateSchema, AccountUpdateSchema
from app.models import utcnow, AccountTypeEnum


@pytest.fixture
def account():
    return SimpleNamespace(
        id=uuid4(),
        icon="account",
        type=AccountTypeEnum.CASH,
        name="Test Account",
        color="Purple",
        agency="1234",
        is_active=True,
        description="Description of the test account",
        account_number="123456789",
        financial_institution="Nubank",
        created_at=utcnow(),
        updated_at=None,
        deleted_at=None,
    )


@pytest.fixture
def create_account_payload():
    return AccountCreateSchema(
        icon="account",
        type=AccountTypeEnum.CASH,
        name="Test Account",
        color="Purple",
        agency="1234",
        is_active=True,
        description="Description of the test account",
        account_number="123456789",
        financial_institution="Nubank",
    )


@pytest.fixture
def update_account_payload(create_account_payload):
    return AccountUpdateSchema.model_validate(
        create_account_payload.model_dump(exclude_unset=True)
    )
