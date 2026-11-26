from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Load, contains_eager, lazyload, selectinload

from app.core.repository import BaseRepository
from app.models import (
    Payment,
    ScheduledTransaction,
    Subcategory,
    Transaction,
    TransactionSeries,
)

from app.domain.transaction.statement.schema import StatementFilterSchema

_PAYMENT_RELATIONS = (
    Payment.beneficiary,
    Payment.destination_institution,
    Payment.payer,
    Payment.receipt,
    Payment.source_institution,
    Payment.subcategory,
)


def _receipt_payment_options(relationship: Any) -> tuple[Load, ...]:
    """Carrega as relações que o `PaymentSchema` lê do pagamento vinculado.

    `lazyload("*")` desliga o `selectin` padrão dos models em todos os níveis, então
    cada relação do pagamento precisa ser pedida explicitamente — sem isso a
    serialização do DTO dispara IO fora do greenlet (`MissingGreenlet`).
    """
    return tuple(
        selectinload(relationship).selectinload(relation)
        for relation in _PAYMENT_RELATIONS
    )


class StatementRepository(BaseRepository[Transaction]):
    model = Transaction

    async def transactions(
        self, *, user_id: UUID, filters: StatementFilterSchema
    ) -> Sequence[Transaction]:
        self.require_owner(user_id)
        return (
            await self.session.scalars(
                select(Transaction)
                .options(
                    lazyload("*"),
                    selectinload(Transaction.account),
                    selectinload(Transaction.credit_card),
                    selectinload(Transaction.subcategory).selectinload(
                        Subcategory.category
                    ),
                    *_receipt_payment_options(Transaction.receipt_payment),
                )
                .where(
                    Transaction.user_id == user_id,
                    Transaction.deleted_at.is_(None),
                    Transaction.expected_on.between(
                        filters.start_date, filters.end_date
                    ),
                )
            )
        ).all()

    async def series(
        self, *, user_id: UUID, filters: StatementFilterSchema
    ) -> Sequence[TransactionSeries]:
        self.require_owner(user_id)
        return (
            await self.session.scalars(
                select(TransactionSeries)
                .options(
                    lazyload("*"),
                    selectinload(TransactionSeries.account),
                    selectinload(TransactionSeries.credit_card),
                    selectinload(TransactionSeries.subcategory).selectinload(
                        Subcategory.category
                    ),
                )
                .where(
                    TransactionSeries.user_id == user_id,
                    TransactionSeries.deleted_at.is_(None),
                    TransactionSeries.start_date <= filters.end_date,
                    or_(
                        TransactionSeries.end_date.is_(None),
                        TransactionSeries.end_date >= filters.start_date,
                    ),
                )
            )
        ).all()

    async def scheduled(
        self,
        *,
        user_id: UUID,
        filters: StatementFilterSchema,
        projected_ranges: dict[UUID, tuple[int, int]],
    ) -> Sequence[tuple[ScheduledTransaction, TransactionSeries]]:
        self.require_owner(user_id)
        replacements = [
            and_(
                ScheduledTransaction.transaction_series_id == series_id,
                ScheduledTransaction.occurrence_index.between(first, last),
            )
            for series_id, (first, last) in projected_ranges.items()
        ]
        result = await self.session.execute(
            select(ScheduledTransaction, TransactionSeries)
            .join(
                TransactionSeries,
                ScheduledTransaction.transaction_series_id == TransactionSeries.id,
            )
            .options(
                lazyload("*"),
                selectinload(ScheduledTransaction.account),
                selectinload(ScheduledTransaction.credit_card),
                selectinload(ScheduledTransaction.subcategory).selectinload(
                    Subcategory.category
                ),
                *_receipt_payment_options(ScheduledTransaction.receipt_payment),
                contains_eager(ScheduledTransaction.transaction_serie).selectinload(
                    TransactionSeries.account
                ),
                contains_eager(ScheduledTransaction.transaction_serie).selectinload(
                    TransactionSeries.credit_card
                ),
                contains_eager(ScheduledTransaction.transaction_serie)
                .selectinload(TransactionSeries.subcategory)
                .selectinload(Subcategory.category),
            )
            .where(
                ScheduledTransaction.user_id == user_id,
                TransactionSeries.user_id == user_id,
                ScheduledTransaction.deleted_at.is_(None),
                TransactionSeries.deleted_at.is_(None),
                or_(
                    ScheduledTransaction.expected_on.between(
                        filters.start_date, filters.end_date
                    ),
                    *replacements,
                ),
            )
        )
        return [(row[0], row[1]) for row in result.all()]
