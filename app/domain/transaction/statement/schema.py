from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import (
    TransactionDirectionEnum,
    TransactionFrequencyUnitEnum,
    TransactionKindEnum,
    TransactionStatusEnum,
)
from app.shared.schemas import FilterPage


class StatementFilterSchema(FilterPage):
    model_config = ConfigDict(extra="forbid")

    limit: int | None = Field(default=12, ge=1)
    order_by: Literal["expected_on", "name", "value"] = "expected_on"
    order: Literal["asc", "desc"] = "desc"
    start_date: date
    end_date: date
    account_id: UUID | None = None
    credit_card_id: UUID | None = None
    subcategory_id: UUID | None = None
    direction: TransactionDirectionEnum | None = None
    status: TransactionStatusEnum | None = None
    search: str | None = Field(default=None, min_length=1, max_length=200)
    only_credit_card: bool | None = None

    @model_validator(mode="after")
    def validate_period(self) -> "StatementFilterSchema":
        days = (self.end_date - self.start_date).days
        if days < 0:
            raise ValueError("end_date must not precede start_date")
        if days >= 366:
            raise ValueError("Statement period must not exceed 366 days inclusive")
        return self


class StatementEntrySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: Literal["TRANSACTION", "SCHEDULED", "PROJECTED"] = "TRANSACTION"
    id: UUID | None = None
    name: str
    note: str | None = None
    value: Decimal
    direction: TransactionDirectionEnum
    status: TransactionStatusEnum
    expected_on: date
    settled_on: date | None = None
    account_id: UUID
    credit_card_id: UUID | None = None
    subcategory_id: UUID | None = None
    transaction_series_id: UUID | None = None
    series_name: str | None = None
    series_kind: TransactionKindEnum | None = None
    installments: int | None = None
    occurrence_index: int | None = None
    occurrence_on: date | None = None


class StatementSeriesSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    note: str | None
    value: Decimal
    direction: TransactionDirectionEnum
    account_id: UUID
    credit_card_id: UUID | None
    subcategory_id: UUID | None
    kind: TransactionKindEnum
    frequency_unit: TransactionFrequencyUnitEnum
    frequency_interval: int = Field(gt=0)
    start_date: date
    end_date: date | None
    installments: int | None = Field(default=None, gt=0)
    week_day: int | None = Field(default=None, ge=1, le=7)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    month: int | None = Field(default=None, ge=1, le=12)

    @model_validator(mode="after")
    def validate_series(self) -> "StatementSeriesSchema":
        if self.kind == TransactionKindEnum.CLOSED and self.installments is None:
            raise ValueError("Closed series require installments")
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("Series end_date must not precede start_date")
        return self
