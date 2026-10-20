from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.domain.institution.schema import InstitutionCreateSchema, InstitutionUpdateSchema
from app.models import utcnow


@pytest.fixture
def institution():
    return SimpleNamespace(
        id=uuid4(),
        name="Electric Company",
        name_code="electric_company",
        created_at=utcnow(),
        updated_at=None,
        deleted_at=None,
    )


@pytest.fixture
def create_institution_payload():
    return InstitutionCreateSchema(name="Electric Company")


@pytest.fixture
def update_institution_payload():
    return InstitutionUpdateSchema(name="Water Company")
