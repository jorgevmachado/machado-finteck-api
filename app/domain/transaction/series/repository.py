from sqlalchemy.orm import selectinload

from app.core.repository import BaseRepository
from app.models import TransactionSeries


class TransactionSeriesRepository(BaseRepository[TransactionSeries]):
    model = TransactionSeries
    filter_fields = ("id", "account_id", "subcategory_id", "credit_card_id", "frequency_unit", "direction", "kind")
    relations = (
        selectinload(TransactionSeries.account),
        selectinload(TransactionSeries.subcategory),
        selectinload(TransactionSeries.credit_card),
    )