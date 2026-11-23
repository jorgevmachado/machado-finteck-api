from pathlib import Path

from pydantic import TypeAdapter

from app.domain.institution.schema import InstitutionCreateSchema


def load_seeds_institutions() -> list[InstitutionCreateSchema]:
    catalog = Path(__file__).with_name("institutions.json")
    return TypeAdapter(list[InstitutionCreateSchema]).validate_json(
        catalog.read_text(encoding="utf-8")
    )
