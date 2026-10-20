import pytest
from pydantic import ValidationError

from app.domain.institution.schema import InstitutionCreateSchema, InstitutionUpdateSchema


@pytest.mark.parametrize("schema_class", [InstitutionCreateSchema, InstitutionUpdateSchema])
@pytest.mark.parametrize("name", ["", "   "])
def test_name_rejects_empty_values(schema_class, name):
    with pytest.raises(ValidationError):
        schema_class(name=name)


def test_create_trims_repeated_whitespace():
    schema = InstitutionCreateSchema(name="  Electric   Company  ")

    assert schema.name == "Electric Company"


def test_update_accepts_an_empty_payload():
    schema = InstitutionUpdateSchema()

    assert schema.model_dump(exclude_unset=True) == {}


def test_update_rejects_explicit_null():
    with pytest.raises(ValidationError):
        InstitutionUpdateSchema(name=None)
