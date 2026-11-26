from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.repository import BaseRepository
from app.models import TransactionDirectionEnum, TransactionKindEnum, TransactionSeries


class TransactionSeriesRepository(BaseRepository[TransactionSeries]):
    model = TransactionSeries
    filter_fields = (
        "id",
        "account_id",
        "subcategory_id",
        "credit_card_id",
        "frequency_unit",
        "direction",
        "kind",
    )
    relations = (
        selectinload(TransactionSeries.account),
        selectinload(TransactionSeries.subcategory),
        selectinload(TransactionSeries.credit_card),
    )

    async def open_candidates(
        self,
        *,
        user_id: UUID,
        account_id: UUID,
        direction: TransactionDirectionEnum,
    ) -> Sequence[TransactionSeries]:
        """Open series of the same account and direction, for name matching.

        Name normalization is a domain rule and stays in the service; this query
        only narrows the candidate set that the service compares.
        """
        self.require_owner(user_id)
        return (
            (
                await self.session.scalars(
                    select(TransactionSeries)
                    .options(*self.relations)
                    .where(
                        TransactionSeries.user_id == user_id,
                        TransactionSeries.deleted_at.is_(None),
                        TransactionSeries.account_id == account_id,
                        TransactionSeries.direction == direction,
                        TransactionSeries.kind == TransactionKindEnum.OPEN,
                    )
                )
            )
            .unique()
            .all()
        )
