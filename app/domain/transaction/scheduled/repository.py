from sqlalchemy.orm import selectinload

from app.core.repository import BaseRepository
from app.models import ScheduledTransaction


class ScheduledTransactionRepository(BaseRepository[ScheduledTransaction]):
    model = ScheduledTransaction
    filter_fields = ("id", "account_id", "subcategory_id", "credit_card_id", "transaction_series_id", "direction", "status")
    relations = (
        selectinload(ScheduledTransaction.account),
        selectinload(ScheduledTransaction.subcategory),
        selectinload(ScheduledTransaction.credit_card),
        selectinload(ScheduledTransaction.transaction_serie),
    )