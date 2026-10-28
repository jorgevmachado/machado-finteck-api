from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.models import AccountTypeEnum


class AccountSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    icon: str | None = None
    type: AccountTypeEnum
    name: str
    color: str | None = None
    agency: str | None = None
    is_active: bool
    description: str | None = None
    account_number: str | None = None
    financial_institution: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class AccountCreateSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    icon: str | None = None
    type: AccountTypeEnum
    name: str
    color: str | None = None
    agency: str | None = None
    is_active: bool = True
    description: str | None = None
    account_number: str | None = None
    financial_institution: str | None = None


class AccountUpdateSchema(AccountCreateSchema):
    type: AccountTypeEnum | None = None
    name: str | None = None

    @field_validator("type", "name", "is_active")
    @classmethod
    def reject_explicit_null(
        cls, value: AccountTypeEnum | str | bool | None
    ) -> AccountTypeEnum | str | bool:
        if value is None:
            raise ValueError("Field cannot be null")
        return value
