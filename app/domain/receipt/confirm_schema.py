"""Response contract for the receipt confirmation.

Lives apart from `receipt.schema` because it aggregates transaction and series
DTOs, and those modules already import the receipt schemas — putting the
envelope there would close an import cycle.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.domain.receipt.payment.schema import PaymentSchema
from app.domain.transaction.scheduled.schema import ScheduledTransactionSchema
from app.domain.transaction.series.schema import TransactionSeriesSchema
from app.domain.transaction.schema import TransactionSchema
from app.models import Payment, ScheduledTransaction, Transaction, TransactionSeries


@dataclass(slots=True)
class ReceiptConfirmOutcome:
    """Entities written by a confirmation, before HTTP serialization.

    The service returns these so cache invalidation can work on the real entities
    and so the route owns the response contract.
    """

    payment: Payment
    transaction: Transaction | None = None
    series: TransactionSeries | None = None
    occurrence: ScheduledTransaction | None = None


class ReceiptConfirmResultSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment: PaymentSchema
    transaction: TransactionSchema | None = None
    series: TransactionSeriesSchema | None = None
    occurrence: ScheduledTransactionSchema | None = None


class ReceiptConfirmConflictSchema(BaseModel):
    type: Literal["SERIES_EXISTS", "OCCURRENCE_EXISTS", "RECEIPT_ALREADY_PROCESSED"]
    existing: dict[str, object] | None = None
    occurrence: dict[str, object] | None = None
