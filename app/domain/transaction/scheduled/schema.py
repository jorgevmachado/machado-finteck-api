from datetime import datetime, date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.account.schema import AccountSchema
from app.domain.category import SubcategorySchema
from app.domain.credit_card.schema import CreditCardSchema
from app.domain.transaction.series.schema import TransactionSeriesSchema
from app.models import TransactionDirectionEnum, TransactionStatusEnum


class ScheduledTransactionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    note: str | None = None
    value: Decimal
    status: TransactionStatusEnum
    account: AccountSchema
    direction: TransactionDirectionEnum
    settled_on: date | None = None
    expected_on: date
    credit_card: CreditCardSchema | None = None
    subcategory: SubcategorySchema | None = None
    occurrence_on: date
    occurrence_index: int
    transaction_serie: TransactionSeriesSchema
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

class ScheduledTransactionRequestCreateSchema(BaseModel):
    name: str
    note: str | None = None
    value: Decimal
    status: TransactionStatusEnum | None = TransactionStatusEnum.PENDING
    direction: TransactionDirectionEnum
    settled_on: date | None = None
    account_id: UUID
    expected_on: date
    occurrence_on: date
    occurrence_index: int
    credit_card_id: UUID | None = None
    subcategory_id: UUID | None = None

class ScheduledTransactionRequestUpdateSchema(ScheduledTransactionRequestCreateSchema):
    name: str | None = None
    value: Decimal | None = None
    direction: TransactionDirectionEnum | None = None
    account_id: UUID | None = None
    expected_on: date | None = None
    occurrence_on: date | None = None
    occurrence_index: int | None = None

class ScheduledTransactionCreateSchema(ScheduledTransactionRequestCreateSchema):
    transaction_series_id: UUID

class ScheduledTransactionUpdateSchema(ScheduledTransactionRequestUpdateSchema):
    transaction_series_id: UUID | None = None