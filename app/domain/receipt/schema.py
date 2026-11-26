from datetime import datetime, date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.domain.receipt.data.schema import ReceiptData, ReceiptDataError
from app.domain.receipt.interpretation.schema import InterpretationResult
from app.models import (
    ReceiptStatusEnum,
    TransactionDirectionEnum,
    TransactionFrequencyUnitEnum,
)
from app.shared.utils.string import text_strip


class ReceiptSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    data: ReceiptData | None = None
    status: ReceiptStatusEnum
    file_name: str
    file_type: str
    file_size: int
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class ReceiptCreateSchema(BaseModel):
    file_name: str
    file_type: str
    file_size: int
    file_hash: str
    status: ReceiptStatusEnum
    data: dict[str, object] | None


class ReceiptUploadSchema(InterpretationResult):
    id: UUID
    data: ReceiptData | None = None
    status: ReceiptStatusEnum
    errors: list[ReceiptDataError]
    file_name: str | None = None
    file_type: str | None = None
    file_size: int
    error_message: str | None = None


class BatchReceiptSchema(BaseModel):
    total: int
    items: list[ReceiptUploadSchema]
    failed: int
    received: int
    processed: int
    processing: int


class ReceiptUpdateSchema(BaseModel):
    """Receipt fields edited on their own, before any confirmation."""

    payer: str
    beneficiary: str
    paid_amount: Decimal
    payment_date: date
    subcategory_id: UUID
    source_institution: str
    destination_institution: str | None = None

    fine: Decimal | None = None
    barcode: str | None = None
    due_date: date | None = None
    discount: Decimal | None = None
    interest: Decimal | None = None
    category: str | None = None
    description: str | None = None
    total_charges: Decimal | None = None
    authentication: str | None = None
    transaction_id: str | None = None
    effective_payer: str | None = None
    document_amount: Decimal | None = None

    @field_validator("payer", "beneficiary", "source_institution")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = text_strip(value)
        if not value:
            raise ValueError("Field cannot be empty")
        return value


class ReceiptConfirmSchema(ReceiptUpdateSchema):
    """Confirmation payload: receipt fields plus the financial entry to create."""

    name: str
    account_id: UUID
    direction: TransactionDirectionEnum = TransactionDirectionEnum.OUT
    expected_on: date | None = None
    credit_card_id: UUID | None = None
    note: str | None = None
    overwrite: bool = False

    transaction_kind: Literal["SIMPLE", "INSTALLMENT", "RECURRING"] = "SIMPLE"
    installment_index: int | None = None
    installments_total: int | None = None
    frequency_unit: TransactionFrequencyUnitEnum | None = None
    frequency_interval: int | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = text_strip(value)
        if not value:
            raise ValueError("Field cannot be empty")
        return value

    @model_validator(mode="after")
    def validate_transaction_kind(self) -> "ReceiptConfirmSchema":
        installment_fields = (self.installment_index, self.installments_total)
        frequency_fields = (self.frequency_unit, self.frequency_interval)

        if self.transaction_kind == "INSTALLMENT":
            if any(field is None for field in installment_fields):
                raise ValueError(
                    "installment_index and installments_total are required "
                    "for INSTALLMENT"
                )
            if any(field is not None for field in frequency_fields):
                raise ValueError(
                    "frequency_unit and frequency_interval are not allowed "
                    "for INSTALLMENT"
                )
            assert self.installment_index is not None
            assert self.installments_total is not None
            if self.installment_index < 1:
                raise ValueError("installment_index must be at least 1")
            if self.installments_total < self.installment_index:
                raise ValueError(
                    "installments_total must be greater than or equal to "
                    "installment_index"
                )
            return self

        if self.transaction_kind == "RECURRING":
            if any(field is None for field in frequency_fields):
                raise ValueError(
                    "frequency_unit and frequency_interval are required for RECURRING"
                )
            if any(field is not None for field in installment_fields):
                raise ValueError(
                    "installment_index and installments_total are not allowed "
                    "for RECURRING"
                )
            assert self.frequency_interval is not None
            if self.frequency_interval < 1:
                raise ValueError("frequency_interval must be at least 1")
            return self

        if any(field is not None for field in (*installment_fields, *frequency_fields)):
            raise ValueError("SIMPLE does not accept installment or frequency fields")
        return self
