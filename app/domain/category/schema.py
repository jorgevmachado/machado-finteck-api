from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
)

from app.shared.utils.string import text_strip


def _normalize_name(value: str) -> str:
    value = text_strip(value)
    if not value:
        raise ValueError("Field cannot be empty")
    return value


CategoryName = Annotated[str, AfterValidator(_normalize_name)]
ColorHex = Annotated[str | None, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
PositiveStrictInt = Annotated[int, Field(strict=True, gt=0)]


class _InputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SubcategoryCreateSchema(_InputSchema):
    name: CategoryName
    icon: str | None = None
    color: ColorHex = None
    is_active: StrictBool = True
    order: PositiveStrictInt


class CategoryCreateSchema(_InputSchema):
    name: CategoryName
    icon: str | None = None
    color: ColorHex = None
    is_active: StrictBool = True
    subcategories: list[SubcategoryCreateSchema] = Field(default_factory=list)

    @field_validator("subcategories")
    @classmethod
    def require_unique_subcategory_orders(
        cls, subcategories: list[SubcategoryCreateSchema]
    ) -> list[SubcategoryCreateSchema]:
        orders = [subcategory.order for subcategory in subcategories]
        if len(orders) != len(set(orders)):
            raise ValueError("Subcategory orders must be unique")
        return subcategories


class SubcategoryReconcileSchema(_InputSchema):
    id: UUID | None = None
    name: CategoryName
    icon: str | None = None
    color: ColorHex = None
    is_active: StrictBool = True
    order: PositiveStrictInt

    @field_validator("id", mode="before")
    @classmethod
    def reject_explicit_null_id(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field cannot be null")
        return value


class CategoryUpdateSchema(_InputSchema):
    name: CategoryName | None = None
    icon: str | None = None
    color: ColorHex = None
    is_active: StrictBool | None = None
    subcategories: list[SubcategoryReconcileSchema] | None = None

    @field_validator("name", "is_active", "subcategories")
    @classmethod
    def reject_explicit_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field cannot be null")
        return value


class CategorySeedSchema(BaseModel):
    created: int
    skipped: int


class SubcategorySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    icon: str | None
    color: str | None
    is_active: bool
    order: int
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class CategorySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    icon: str | None
    color: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
    subcategories: list[SubcategorySchema]
