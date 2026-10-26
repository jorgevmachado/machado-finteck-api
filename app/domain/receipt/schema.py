from datetime import datetime, date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.receipt.data.schema import ReceiptData, ReceiptDataError
from app.domain.receipt.interpretation.schema import InterpretationResult
from app.models import ReceiptStatusEnum

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

class ReceiptConfirmSchema(BaseModel):
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
    description: str | None = None
    total_charges: Decimal | None = None
    authentication: str | None = None
    transaction_id: str | None = None
    effective_payer: str | None = None
    document_amount: Decimal | None = None
