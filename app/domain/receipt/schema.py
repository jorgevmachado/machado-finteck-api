from datetime import datetime
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