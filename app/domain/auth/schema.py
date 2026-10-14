from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.models.auth.enums import StatusEnum


class RegisterSchema(BaseModel):
    name: str
    email: EmailStr
    username: str
    date_of_birth: datetime
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        return value


class LoginSchema(BaseModel):
    credential: str
    password: str


class LoginResponseSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthInfoSchema(BaseModel):
    total: int
    total_success: int
    total_failures: int
    failed_attempts: int
    last_authentication_at: datetime | None = None


class AuthSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    name: str
    info: AuthInfoSchema | None = None
    email: str
    status: StatusEnum
    username: str
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
