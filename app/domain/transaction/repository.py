from sqlalchemy.orm import selectinload

from app.core.repository import BaseRepository
from app.models import Transaction


class TransactionRepository(BaseRepository[Transaction]):
    model = Transaction
    filter_fields = ("id", "account_id", "subcategory_id", "credit_card_id", "direction", "status")
    relations = (
        selectinload(Transaction.account),
        selectinload(Transaction.subcategory),
        selectinload(Transaction.credit_card),
    )