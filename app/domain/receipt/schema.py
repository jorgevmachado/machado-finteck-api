from uuid import UUID

from app.domain.receipt.interpretation.schema import InterpretationResult


class ReceiptUploadSchema(InterpretationResult):
    filename: str | None
    user_id: UUID
    status: str
    file_hash: str
