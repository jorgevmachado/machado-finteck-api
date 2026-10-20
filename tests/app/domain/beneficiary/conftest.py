from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.domain.beneficiary.schema import BeneficiaryCreateSchema, BeneficiaryUpdateSchema
from app.models import utcnow


@pytest.fixture
def beneficiary():
    return SimpleNamespace(
        id=uuid4(),
        name="Electric Company",
        name_code="electric_company",
        created_at=utcnow(),
        updated_at=None,
        deleted_at=None,
    )


@pytest.fixture
def create_beneficiary_payload():
    return BeneficiaryCreateSchema(name="Electric Company")


@pytest.fixture
def update_beneficiary_payload():
    return BeneficiaryUpdateSchema(name="Water Company")
