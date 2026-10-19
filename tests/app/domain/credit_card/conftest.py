from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.domain.credit_card.schema import CreditCardCreateSchema, CreditCardUpdateSchema
from app.models import utcnow, CreditCardBrandEnum


@pytest.fixture
def credit_card():
    return SimpleNamespace(
        id=uuid4(),
        icon="credit_card",
        brand=CreditCardBrandEnum.VISA,
        name="Test Credit Card",
        color="Purple",
        is_active=True,
        description="Description of the test credit card",
        last_four_digits="1234",
        closing_day=15,
        due_day=25,
        limit=5000,
        created_at=utcnow(),
        updated_at=None,
        deleted_at=None,
    )


@pytest.fixture
def create_credit_card_payload():
    return CreditCardCreateSchema(
        icon="credit_card",
        brand=CreditCardBrandEnum.VISA,
        name="Test Credit Card",
        color="Purple",
        is_active=True,
        description="Description of the test credit card",
        last_four_digits="1234",
        closing_day=15,
        due_day=25,
        limit=5000,
    )


@pytest.fixture
def update_credit_card_payload(create_credit_card_payload):
    return CreditCardUpdateSchema.model_validate(
        create_credit_card_payload.model_dump(exclude_unset=True)
    )
