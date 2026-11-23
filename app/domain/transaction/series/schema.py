from datetime import datetime, date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.domain.account.schema import AccountSchema
from app.domain.category import SubcategorySchema
from app.domain.credit_card.schema import CreditCardSchema
from app.models import (
    TransactionDirectionEnum,
    TransactionKindEnum,
    TransactionFrequencyUnitEnum,
)


class TransactionSeriesSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    note: str | None = None
    kind: TransactionKindEnum
    value: Decimal
    month: int | None = None
    account: AccountSchema
    week_day: int | None = None
    end_date: date | None = None
    direction: TransactionDirectionEnum
    start_date: date
    credit_card: CreditCardSchema | None = None
    subcategory: SubcategorySchema | None = None
    day_of_month: int | None = None
    installments: int | None = None
    frequency_unit: TransactionFrequencyUnitEnum
    frequency_interval: int
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class TransactionSeriesCreateSchema(BaseModel):
    kind: TransactionKindEnum
    name: str
    note: str | None = None
    value: Decimal
    month: int | None = None
    week_day: int | None = None
    end_date: date | None = None
    direction: TransactionDirectionEnum
    start_date: date
    account_id: UUID
    day_of_month: int | None = None
    installments: int | None = None
    credit_card_id: UUID | None = None
    subcategory_id: UUID | None = None
    frequency_unit: TransactionFrequencyUnitEnum
    frequency_interval: int


class TransactionSeriesUpdateSchema(TransactionSeriesCreateSchema):
    kind: TransactionKindEnum | None = None
    start_date: date | None = None
    name: str | None = None
    value: Decimal | None = None
    end_date: date | None = None
    direction: TransactionDirectionEnum | None = None
    account_id: UUID | None = None
    expected_on: date | None = None
    frequency_unit: TransactionFrequencyUnitEnum | None = None
    frequency_interval: int | None = None

    @field_validator("start_date")
    @classmethod
    def reject_null_start_date(cls, value: date | None) -> date:
        if value is None:
            raise ValueError("Field cannot be null")
        return value
