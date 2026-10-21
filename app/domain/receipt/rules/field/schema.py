from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from app.shared.schemas import ResponseSchema

from app.domain.receipt.rules.configuration.schema import (
    FieldConfiguration,
    ReceiptNotFoundConfiguration,
    ReceiptConstantConfiguration,
    ReceiptSourceConfiguration,
)
from app.domain.receipt.rules.enums import (
    MONEY_FIELDS,
    ReceiptParser,
    DATE_FIELDS,
    ReceiptFieldName,
)


Pattern = Annotated[str, Field(min_length=1, max_length=2000)]


class ReceiptFieldRuleCreateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: ReceiptFieldName
    configuration: FieldConfiguration
    is_active: StrictBool = True

    @model_validator(mode="after")
    def validate_parser(self) -> Self:
        configuration = self.configuration
        if isinstance(configuration, ReceiptNotFoundConfiguration):
            return self
        if isinstance(configuration, ReceiptSourceConfiguration):
            if self.field_name != ReceiptFieldName.SOURCE_INSTITUTION:
                raise ValueError(
                    "Source strategy is only supported for source_institution"
                )
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


class ReceiptFieldRuleSchema(ResponseSchema, ReceiptFieldRuleCreateSchema):
    is_active: bool


class ReceiptFieldRuleReconcileSchema(ReceiptFieldRuleCreateSchema):
    id: UUID | None = None

    @field_validator("id", mode="before")
    @classmethod
    def reject_null_id(cls, value: object) -> object:
        if value is None:
            raise ValueError("ID must be omitted instead of null")
        return value
