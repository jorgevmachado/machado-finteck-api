from pathlib import Path

from pydantic import TypeAdapter

from app.domain.category.schema import CategoryCreateSchema


def load_default_categories() -> list[CategoryCreateSchema]:
    catalog = Path(__file__).with_name("default_categories.json")
    return TypeAdapter(list[CategoryCreateSchema]).validate_json(
        catalog.read_text(encoding="utf-8")
    )
