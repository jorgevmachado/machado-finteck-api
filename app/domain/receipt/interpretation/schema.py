from pydantic import BaseModel
from typing import Literal
from uuid import UUID

from app.domain.receipt.data.schema import ReceiptData, ReceiptDataError
from app.domain.receipt.receipt_interpretation_profile.schema import (
    ReceiptInterpretationProfileSchema,
)


class InterpretationConfigurationSnapshot(BaseModel):
    version: Literal[1] = 1
    selected_profile_id: UUID | None
    profiles: list[ReceiptInterpretationProfileSchema]


class InterpretationResult(BaseModel):
    data: ReceiptData
    errors: list[ReceiptDataError]
    configuration: InterpretationConfigurationSnapshot | None = None
