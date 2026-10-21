from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from app.shared.schemas import ResponseSchema

from app.domain.receipt.rules.validate import validate_pattern

Pattern = Annotated[str, Field(min_length=1, max_length=2000)]

class ReceiptIdentificationRuleCreateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pattern: Pattern
    weight: Annotated[int, Field(strict=True, gt=0)]
    is_active: StrictBool = True

    @field_validator("pattern")
    @classmethod
    def validate_regex(cls, pattern: str) -> str:
        validate_pattern(pattern)
        return pattern

class ReceiptIdentificationRuleSchema(
    ResponseSchema, ReceiptIdentificationRuleCreateSchema
):
    is_active: bool

class ReceiptIdentificationRuleReconcileSchema(ReceiptIdentificationRuleCreateSchema):
    id: UUID | None = None

    @field_validator("id", mode="before")
    @classmethod
    def reject_null_id(cls, value: object) -> object:
        if value is None:
            raise ValueError("ID must be omitted instead of null")
        return value