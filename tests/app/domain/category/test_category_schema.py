from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.category.schema import (
    CategoryCreateSchema,
    CategorySchema,
    CategoryUpdateSchema,
    SubcategoryCreateSchema,
    SubcategoryReconcileSchema,
)


def test_category_create_applies_defaults_and_normalizes_names():
    schema = CategoryCreateSchema(
        name="  Casa   principal ",
        subcategories=[{"name": "  Contas   fixas ", "order": 1}],
    )

    assert schema.name == "Casa principal"
    assert schema.is_active is True
    assert schema.icon is None
    assert schema.color is None
    assert schema.subcategories[0].name == "Contas fixas"
    assert schema.subcategories[0].is_active is True
    assert schema.subcategories[0].icon is None
    assert schema.subcategories[0].color is None


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Casa", "is_active": None},
        {"name": "Casa", "subcategories": None},
        {
            "name": "Casa",
            "subcategories": [{"name": "Contas", "order": 1, "is_active": None}],
        },
    ],
)
def test_creation_rejects_null_instead_of_applying_defaults(payload):
    with pytest.raises(ValidationError):
        CategoryCreateSchema(**payload)


def test_category_create_defaults_subcategories_to_empty_list():
    schema = CategoryCreateSchema(name="Casa")

    assert schema.subcategories == []


def test_category_create_rejects_duplicate_child_orders():
    with pytest.raises(ValidationError, match="orders must be unique"):
        CategoryCreateSchema(
            name="Casa",
            subcategories=[
                {"name": "Ativas", "order": 1},
                {"name": "Inativas", "order": 1, "is_active": False},
            ],
        )


def test_explicit_false_and_valid_color_are_preserved():
    schema = CategoryCreateSchema(
        name="Casa",
        color="#aB123F",
        is_active=False,
        subcategories=[
            {
                "name": "Contas",
                "order": 5,
                "color": "#ABCDEF",
                "is_active": False,
            }
        ],
    )

    assert schema.color == "#aB123F"
    assert schema.is_active is False
    assert schema.subcategories[0].color == "#ABCDEF"
    assert schema.subcategories[0].is_active is False


@pytest.mark.parametrize(
    "schema_class,payload",
    [
        (CategoryCreateSchema, {"name": " \t "}),
        (SubcategoryCreateSchema, {"name": "\n"}),
        (
            CategoryCreateSchema,
            {"name": "Casa", "color": "#FFF"},
        ),
        (
            CategoryCreateSchema,
            {"name": "Casa", "color": "aabbcc"},
        ),
        (
            SubcategoryCreateSchema,
            {"name": "Contas", "order": 1, "color": "#12345G"},
        ),
    ],
)
def test_creation_rejects_empty_names_and_invalid_colors(schema_class, payload):
    with pytest.raises(ValidationError):
        schema_class(**payload)


@pytest.mark.parametrize("order", [True, 1.5, "1", 0, -1])
def test_child_creation_requires_a_strict_positive_integer_order(order):
    with pytest.raises(ValidationError):
        SubcategoryCreateSchema(name="Contas", order=order)


def test_child_creation_accepts_order_gaps():
    assert SubcategoryCreateSchema(name="Contas", order=5).order == 5


def test_reconcile_schema_uses_omitted_id_for_a_new_child():
    schema = SubcategoryReconcileSchema(name="Contas", order=1)

    assert schema.id is None


def test_reconcile_schema_accepts_existing_uuid_but_rejects_explicit_null():
    child_id = uuid4()

    assert (
        SubcategoryReconcileSchema(id=child_id, name="Contas", order=1).id == child_id
    )
    with pytest.raises(ValidationError):
        SubcategoryReconcileSchema(id=None, name="Contas", order=1)


def test_update_accepts_omitted_child_list_and_tracks_explicit_empty_list():
    schema = CategoryUpdateSchema(subcategories=[])

    assert schema.model_fields_set == {"subcategories"}
    assert schema.name is None
    assert schema.is_active is None
    assert schema.icon is None
    assert schema.color is None

    omitted = CategoryUpdateSchema(name="Novo nome")
    assert omitted.subcategories is None
    assert omitted.model_dump(exclude_unset=True) == {"name": "Novo nome"}
    assert CategoryUpdateSchema().model_fields_set == set()
    with pytest.raises(ValidationError):
        CategoryUpdateSchema(subcategories=None)


@pytest.mark.parametrize("field", ["name", "is_active"])
def test_update_rejects_explicit_null_for_required_root_fields(field):
    with pytest.raises(ValidationError):
        CategoryUpdateSchema(subcategories=[], **{field: None})


def test_update_allows_null_to_clear_root_visual_fields():
    schema = CategoryUpdateSchema(subcategories=[], icon=None, color=None)

    assert schema.model_fields_set == {"subcategories", "icon", "color"}


@pytest.mark.parametrize(
    "schema_class,payload",
    [
        (CategoryCreateSchema, {"name": "Casa", "id": str(uuid4())}),
        (CategoryCreateSchema, {"name": "Casa", "created_at": "2026-01-01"}),
        (
            CategoryCreateSchema,
            {
                "name": "Casa",
                "subcategories": [{"name": "Contas", "order": 1, "id": str(uuid4())}],
            },
        ),
        (CategoryCreateSchema, {"name": "Casa", "user_id": str(uuid4())}),
        (CategoryUpdateSchema, {"subcategories": [], "created_at": "2026-01-01"}),
        (
            CategoryUpdateSchema,
            {
                "subcategories": [
                    {"name": "Contas", "order": 1, "category_id": str(uuid4())}
                ]
            },
        ),
    ],
)
def test_input_schemas_forbid_server_managed_and_unknown_fields(schema_class, payload):
    with pytest.raises(ValidationError):
        schema_class(**payload)


def test_category_response_reads_public_fields_from_attributes():
    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    child_id = uuid4()
    category_id = uuid4()
    child = SimpleNamespace(
        id=child_id,
        name="Contas",
        icon=None,
        color="#123456",
        is_active=True,
        order=1,
        created_at=created_at,
        updated_at=None,
        deleted_at=None,
        category_id=category_id,
    )
    category = SimpleNamespace(
        id=category_id,
        name="Casa",
        icon=None,
        color=None,
        is_active=True,
        created_at=created_at,
        updated_at=None,
        deleted_at=None,
        user_id=uuid4(),
        subcategories=[child],
    )

    schema = CategorySchema.model_validate(category)

    assert schema.id == category_id
    assert schema.subcategories[0].id == child_id
    assert "user_id" not in schema.model_dump()
    assert "category_id" not in schema.subcategories[0].model_dump()
