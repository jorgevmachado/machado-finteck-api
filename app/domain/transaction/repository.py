from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.repository import BaseRepository
from app.domain.transaction.scheduled.repository import ScheduledTransactionRepository
from app.domain.transaction.series.repository import TransactionSeriesRepository
from app.models import (
    Account,
    Category,
    CreditCard,
    Subcategory,
    Transaction,
    TransactionSeries,
)


class TransactionRepository(BaseRepository[Transaction]):
    model = Transaction
    filter_fields = (
        "id",
        "account_id",
        "subcategory_id",
        "credit_card_id",
        "direction",
        "status",
    )
    relations = (
        selectinload(Transaction.account),
        selectinload(Transaction.subcategory),
        selectinload(Transaction.credit_card),
    )

    async def seed_account_ids(self, *, user_id: UUID) -> list[UUID]:
        self.require_owner(user_id)
        return list(
            await self.session.scalars(
                select(Account.id)
                .where(
                    Account.user_id == user_id,
                    Account.is_active.is_(True),
                    Account.deleted_at.is_(None),
                )
                .order_by(Account.id)
            )
        )

    async def seed_credit_card_ids(self, *, user_id: UUID) -> list[UUID]:
        self.require_owner(user_id)
        return list(
            await self.session.scalars(
                select(CreditCard.id)
                .where(
                    CreditCard.user_id == user_id,
                    CreditCard.is_active.is_(True),
                    CreditCard.deleted_at.is_(None),
                )
                .order_by(CreditCard.id)
            )
        )

    async def seed_subcategories(self, *, user_id: UUID) -> dict[str, UUID]:
        self.require_owner(user_id)
        rows = await self.session.execute(
            select(Subcategory.name, Subcategory.id)
            .join(Category, Subcategory.category_id == Category.id)
            .where(
                Category.user_id == user_id,
                Category.is_active.is_(True),
                Category.deleted_at.is_(None),
                Subcategory.is_active.is_(True),
                Subcategory.deleted_at.is_(None),
            )
            .order_by(Category.id, Subcategory.id)
        )
        matches: dict[str, UUID] = {}
        for name, identifier in rows:
            matches.setdefault(name, identifier)
        return matches

    async def save_seed(
        self,
        *,
        transactions: list[Transaction],
        series: list[TransactionSeries],
        user_id: UUID,
    ) -> None:
        self.require_owner(user_id)
        self._require_transaction()
        series_repository = TransactionSeriesRepository(self.session)
        scheduled_repository = ScheduledTransactionRepository(self.session)
        for transaction in transactions:
            self._check_entity(transaction, user_id)
        for entity in series:
            series_repository._check_entity(entity, user_id)
            for occurrence in entity.scheduled_transactions:
                scheduled_repository._check_entity(occurrence, user_id)
                if occurrence.transaction_series_id != entity.id:
                    raise ValueError(
                        "Scheduled transaction belongs to a different series"
                    )
        self.session.add_all([*transactions, *series])
        await self.session.flush()
