from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.shared.utils.string import text_strip


class InstitutionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class InstitutionCreateSchema(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = text_strip(value)
        if not value:
            raise ValueError("Field cannot be empty")
        return value


class InstitutionUpdateSchema(BaseModel):
    name: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Field cannot be null")
        value = text_strip(value)
        if not value:
            raise ValueError("Field cannot be empty")
        return value
