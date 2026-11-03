from datetime import datetime, date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.account.schema import AccountSchema
from app.domain.category import SubcategorySchema
from app.domain.credit_card.schema import CreditCardSchema
from app.models import TransactionDirectionEnum, TransactionStatusEnum


class TransactionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    note: str | None = None
    value: Decimal
    status: TransactionStatusEnum
    account: AccountSchema
    direction: TransactionDirectionEnum
    credit_card: CreditCardSchema | None = None
    subcategory: SubcategorySchema | None = None
    settled_on: date | None = None
    expected_on: date
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

class TransactionCreateSchema(BaseModel):
    name: str
    note: str | None = None
    value: Decimal
    status: TransactionStatusEnum | None = TransactionStatusEnum.PENDING
    direction: TransactionDirectionEnum
    settled_on: date | None = None
    account_id: UUID
    expected_on: date
    credit_card_id: UUID | None = None
    subcategory_id: UUID | None = None

class TransactionUpdateSchema(TransactionCreateSchema):
    name: str | None = None
    value: Decimal | None = None
    direction: TransactionDirectionEnum | None = None
    account_id: UUID | None = None
    expected_on: date | None = None