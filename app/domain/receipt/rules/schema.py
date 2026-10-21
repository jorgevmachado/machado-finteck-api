from __future__ import annotations

from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from app.domain.receipt.rules.enums import ProfileScope
from app.domain.receipt.rules.field.schema import (
    ReceiptFieldRuleCreateSchema,
    ReceiptFieldRuleSchema,
    ReceiptFieldRuleReconcileSchema,
)
from app.domain.receipt.rules.identification.schema import (
    ReceiptIdentificationRuleCreateSchema,
    ReceiptIdentificationRuleSchema,
    ReceiptIdentificationRuleReconcileSchema,
)
from app.domain.receipt.rules.validate import normalize_name, normalize_code
from app.shared.schemas import ResponseSchema, FilterPage

ProfileName = Annotated[str, AfterValidator(normalize_name)]
InstitutionCode = Annotated[str, AfterValidator(normalize_code)]
Pattern = Annotated[str, Field(min_length=1, max_length=2000)]


class _InputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ReceiptRulesInputSchema(_InputSchema):
    name: ProfileName
    is_active: StrictBool = True
    identification_rules: list[ReceiptIdentificationRuleCreateSchema] = Field(
        default_factory=list, max_length=100
    )
    field_rules: list[ReceiptFieldRuleCreateSchema] = Field(
        default_factory=list, max_length=100
    )

    @field_validator("field_rules")
    @classmethod
    def validate_unique_fields(
        cls, rules: list[ReceiptFieldRuleCreateSchema]
    ) -> list[ReceiptFieldRuleCreateSchema]:
        fields = [rule.field_name for rule in rules]
        if len(fields) != len(set(fields)):
            raise ValueError("Field names must be unique within a profile")
        return rules


class ReceiptRulesCreateSchema(_ReceiptRulesInputSchema):
    institution_code: InstitutionCode


class ReceiptRulesSeedEntrySchema(_ReceiptRulesInputSchema):
    institution_code: InstitutionCode | None

    @model_validator(mode="after")
    def validate_general(self) -> ReceiptRulesSeedEntrySchema:
        if self.institution_code is None and self.identification_rules:
            raise ValueError("General profile cannot contain identification rules")
        return self


class ReceiptRulesUpdateSchema(_InputSchema):
    name: ProfileName | None = None
    is_active: StrictBool | None = None
    identification_rules: list[ReceiptIdentificationRuleReconcileSchema] | None = Field(
        default=None, max_length=100
    )
    field_rules: list[ReceiptFieldRuleReconcileSchema] | None = Field(
        default=None, max_length=100
    )

    @field_validator("name", "is_active", "identification_rules", "field_rules")
    @classmethod
    def reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field cannot be null")
        return value


class ReceiptRulesSchema(ResponseSchema):
    name: str
    institution_code: str | None
    scope: ProfileScope
    identification_rules: list[ReceiptIdentificationRuleSchema]
    field_rules: list[ReceiptFieldRuleSchema]

    @model_validator(mode="before")
    @classmethod
    def derive_scope(cls, value: object) -> object:
        if isinstance(value, dict):
            return value
        result = {
            **{
                field: getattr(value, field)
                for field in cls.model_fields
                if field != "scope"
            },
            "scope": "system" if getattr(value, "user_id") is None else "private",
        }
        for collection in ("field_rules", "identification_rules"):
            result[collection] = sorted(
                [
                    child
                    for child in getattr(value, collection)
                    if child.deleted_at is None
                ],
                key=lambda child: (child.created_at, child.id),
            )
        return result


class ReceiptRulesFilter(FilterPage):
    limit: int | None = Field(12, ge=1)
    name: ProfileName | None = None
    institution_code: InstitutionCode | None = None
    scope: ProfileScope | None = None


class ReceiptRulesSeedSchema(BaseModel):
    created: int
    skipped: int
