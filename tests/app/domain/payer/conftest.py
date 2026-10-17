from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.domain.payer.schema import PayerCreateSchema, PayerUpdateSchema
from app.models import utcnow


@pytest.fixture
def payer():
    return SimpleNamespace(
        id=uuid4(),
        name="Electric Company",
        name_code="electric_company",
        created_at=utcnow(),
        updated_at=None,
        deleted_at=None,
    )


@pytest.fixture
def create_payer_payload():
    return PayerCreateSchema(name="Electric Company")


@pytest.fixture
def update_payer_payload():
    return PayerUpdateSchema(name="Water Company")
