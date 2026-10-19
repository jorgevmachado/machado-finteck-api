from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.models import CreditCardBrandEnum


class CreditCardSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    icon: str | None = None
    brand: CreditCardBrandEnum
    name: str
    limit: int | None = None
    color: str | None = None
    due_day: int
    is_active: bool
    closing_day: int
    description: str | None = None
    last_four_digits: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

class CreditCardCreateSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    icon: str | None = None
    brand: CreditCardBrandEnum
    name: str
    limit: int | None = None
    color: str | None = None
    due_day: int
    is_active: bool | None = True
    closing_day: int
    description: str | None = None
    last_four_digits: str | None = None


class CreditCardUpdateSchema(CreditCardCreateSchema):
    brand: CreditCardBrandEnum | None = None
    name: str | None = None
    due_day: int | None = None
    closing_day: int | None = None

    @field_validator("brand", "name", "due_day", "closing_day")
    @classmethod
    def reject_explicit_null(
        cls, value: CreditCardBrandEnum | str | None
    ) -> CreditCardBrandEnum | str:
        if value is None:
            raise ValueError("Field cannot be null")
        return value
