from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from app.domain.receipt.receipt_interpretation_profile.enums import (
    DATE_FIELDS,
    MONEY_FIELDS,
    ProfileScope,
    ReceiptFieldName,
    ReceiptParser,
)
from app.shared.schemas import FilterPage
from app.shared.utils.string import text_strip


def normalize_name(value: str) -> str:
    value = text_strip(value)
    if not value:
        raise ValueError("Name cannot be empty")
    return value


def normalize_code(value: str) -> str:
    value = value.strip().upper()
    if re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,63}", value) is None:
        raise ValueError("Invalid institution code")
    return value


def validate_pattern(value: str) -> re.Pattern[str]:
    if not value.strip():
        raise ValueError("Pattern cannot be empty")
    try:
        return re.compile(value, re.IGNORECASE)
    except (re.error, RecursionError, OverflowError) as exception:
        raise ValueError("Invalid regular expression") from exception


ProfileName = Annotated[str, AfterValidator(normalize_name)]
InstitutionCode = Annotated[str, AfterValidator(normalize_code)]
Pattern = Annotated[str, Field(min_length=1, max_length=2000)]


class _InputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReceiptFieldConfiguration(_InputSchema):
    strategy: Literal["regex"]
    patterns: list[Pattern] = Field(min_length=1, max_length=20)
    parser: ReceiptParser
    normalization: Literal["strip", "remove_whitespace", "ocr_day"] = "strip"
    fallback_field: Literal["payer", "paid_amount"] | None = None

    @field_validator("patterns")
    @classmethod
    def validate_patterns(cls, patterns: list[str]) -> list[str]:
        for pattern in patterns:
            if "value" not in validate_pattern(pattern).groupindex:
                raise ValueError("Pattern must contain a named group 'value'")
        return patterns


class ReceiptConstantConfiguration(_InputSchema):
    strategy: Literal["constant"]
    value: Annotated[str, Field(min_length=1, max_length=200)]

    @field_validator("value")
    @classmethod
    def normalize_value(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Constant value cannot be blank")
        return value.strip()


class ReceiptNotFoundConfiguration(_InputSchema):
    strategy: Literal["not_found"]


FieldConfiguration = Annotated[
    ReceiptFieldConfiguration
    | ReceiptConstantConfiguration
    | ReceiptNotFoundConfiguration,
    Field(discriminator="strategy"),
]


class ReceiptFieldRuleCreateSchema(_InputSchema):
    field_name: ReceiptFieldName
    configuration: FieldConfiguration
    is_active: StrictBool = True

    @model_validator(mode="after")
    def validate_parser(self) -> Self:
        configuration = self.configuration
        if isinstance(configuration, ReceiptNotFoundConfiguration):
            return self
        if isinstance(configuration, ReceiptConstantConfiguration):
            if self.field_name != ReceiptFieldName.SOURCE_INSTITUTION:
                raise ValueError("Constants are only supported for source_institution")
            return self
        if self.field_name in MONEY_FIELDS:
            allowed = {ReceiptParser.DECIMAL_BR}
        elif self.field_name in DATE_FIELDS:
            allowed = {
                ReceiptParser.DATE_NUMERIC_BR,
                ReceiptParser.DATE_MONTH_NAME_PT_BR,
            }
        else:
            allowed = {ReceiptParser.TEXT}
        if configuration.parser not in allowed:
            raise ValueError("Parser is incompatible with the receipt field")
        if configuration.normalization == "remove_whitespace":
            if self.field_name != ReceiptFieldName.BARCODE:
                raise ValueError("Whitespace removal is only supported for barcode")
        if configuration.normalization == "ocr_day":
            if configuration.parser != ReceiptParser.DATE_MONTH_NAME_PT_BR:
                raise ValueError("OCR day normalization requires month-name dates")
        expected_fallback = {
            ReceiptFieldName.EFFECTIVE_PAYER: "payer",
            ReceiptFieldName.DOCUMENT_AMOUNT: "paid_amount",
        }.get(self.field_name)
        if (
            configuration.fallback_field is not None
            and configuration.fallback_field != expected_fallback
        ):
            raise ValueError("Unsupported fallback field")
        return self


class ReceiptIdentificationRuleCreateSchema(_InputSchema):
    pattern: Pattern
    weight: Annotated[int, Field(strict=True, gt=0)]
    is_active: StrictBool = True

    @field_validator("pattern")
    @classmethod
    def validate_regex(cls, pattern: str) -> str:
        validate_pattern(pattern)
        return pattern


class ReceiptFieldRuleReconcileSchema(ReceiptFieldRuleCreateSchema):
    id: UUID | None = None

    @field_validator("id", mode="before")
    @classmethod
    def reject_null_id(cls, value: object) -> object:
        if value is None:
            raise ValueError("ID must be omitted instead of null")
        return value


class ReceiptIdentificationRuleReconcileSchema(ReceiptIdentificationRuleCreateSchema):
    id: UUID | None = None

    @field_validator("id", mode="before")
    @classmethod
    def reject_null_id(cls, value: object) -> object:
        if value is None:
            raise ValueError("ID must be omitted instead of null")
        return value


class ReceiptInterpretationProfileCreateSchema(_InputSchema):
    name: ProfileName
    institution_code: InstitutionCode
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


class ReceiptInterpretationProfileUpdateSchema(_InputSchema):
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


class ReceiptInterpretationProfileFilter(FilterPage):
    limit: int | None = Field(12, ge=1)
    name: ProfileName | None = None
    institution_code: InstitutionCode | None = None
    scope: ProfileScope | None = None


class _ResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class ReceiptFieldRuleSchema(_ResponseSchema, ReceiptFieldRuleCreateSchema):
    pass


class ReceiptIdentificationRuleSchema(
    _ResponseSchema, ReceiptIdentificationRuleCreateSchema
):
    pass


class ReceiptInterpretationProfileSchema(_ResponseSchema):
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
