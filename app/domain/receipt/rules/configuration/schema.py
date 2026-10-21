from typing import Literal, Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.receipt.rules.enums import ReceiptParser
from app.domain.receipt.rules.validate import validate_pattern

Pattern = Annotated[str, Field(min_length=1, max_length=2000)]


class ReceiptFieldConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
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


class ReceiptConstantConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy: Literal["constant"]
    value: Annotated[str, Field(min_length=1, max_length=200)]

    @field_validator("value")
    @classmethod
    def normalize_value(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Constant value cannot be blank")
        return value.strip()


class ReceiptNotFoundConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy: Literal["not_found"]


class ReceiptTextMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contains: Annotated[str, Field(min_length=1, max_length=200)]
    value: Annotated[str, Field(min_length=1, max_length=200)]

    @field_validator("contains", "value")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Mapping text cannot be blank")
        return value.strip()


class ReceiptSourceConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy: Literal["source"]
    identified_value: Annotated[str, Field(min_length=1, max_length=200)]
    matches: list[ReceiptTextMapping] = Field(default_factory=list, max_length=20)
    extraction: ReceiptFieldConfiguration | None = None
    mappings: list[ReceiptTextMapping] = Field(default_factory=list, max_length=20)

    @field_validator("identified_value")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Identified value cannot be blank")
        return value.strip()

    @field_validator("extraction")
    @classmethod
    def text_extraction_only(
        cls, value: ReceiptFieldConfiguration | None
    ) -> ReceiptFieldConfiguration | None:
        if value is not None and (
            value.parser != ReceiptParser.TEXT
            or value.normalization != "strip"
            or value.fallback_field is not None
        ):
            raise ValueError("Source extraction requires plain text without fallback")
        return value


FieldConfiguration = Annotated[
    ReceiptFieldConfiguration
    | ReceiptConstantConfiguration
    | ReceiptNotFoundConfiguration
    | ReceiptSourceConfiguration,
    Field(discriminator="strategy"),
]
