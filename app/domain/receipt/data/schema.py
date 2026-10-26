from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel

from app.domain.receipt.data.enums import DataStatusEnum

T = TypeVar("T")

class DataField(BaseModel, Generic[T]):
    value: T | None = None
    status: DataStatusEnum


class ReceiptData(BaseModel):
    fine: DataField[Decimal]
    payer: DataField[str]
    barcode: DataField[str]
    due_date: DataField[date]
    discount: DataField[Decimal]
    interest: DataField[Decimal]
    category: DataField[str]
    description: DataField[str]
    paid_amount: DataField[Decimal]
    beneficiary: DataField[str]
    payment_date: DataField[date]
    total_charges: DataField[Decimal]
    authentication: DataField[str]
    transaction_id: DataField[str]
    effective_payer: DataField[str]
    document_amount: DataField[Decimal]
    source_institution: DataField[str]
    destination_institution: DataField[str]

class ReceiptDataError(BaseModel):
    field: str
    status: DataStatusEnum