from __future__ import annotations

import logging
from uuid import UUID

from app.core.logging import LoggingParams
from app.core.service import BaseService

from app.domain.transaction.series.repository import TransactionSeriesRepository
from app.domain.transaction.series.schema import (
    TransactionSeriesCreateSchema,
    TransactionSeriesSchema,
    TransactionSeriesUpdateSchema,
)
from app.models import (
    TransactionDirectionEnum,
    TransactionSeries,
    TransactionFrequencyUnitEnum,
    User,
)
from app.shared.utils.string import to_snake_case

logger = logging.getLogger(__name__)


class TransactionSeriesService(
    BaseService[
        TransactionSeries, TransactionSeriesCreateSchema, TransactionSeriesUpdateSchema
    ]
):
    repository_class = TransactionSeriesRepository

    def __init__(self, repository: TransactionSeriesRepository) -> None:
        super().__init__(
            repository,
            alias="TransactionSeries",
            logger_params=LoggingParams(
                logger=logger,
                service="TransactionService",
                operation="transaction_series",
            ),
            schema_class=TransactionSeriesSchema,
            cache_prefix="transaction_series",
        )

    def _build_entity(
        self, user_id: UUID, data: dict[str, object]
    ) -> TransactionSeries:
        payload = TransactionSeriesCreateSchema.model_validate(data)
        week_day = (
            payload.week_day
            if payload.frequency_unit == TransactionFrequencyUnitEnum.WEEK
            else None
        )
        day_of_month = (
            payload.day_of_month
            if payload.frequency_unit != TransactionFrequencyUnitEnum.WEEK
            else None
        )
        month = (
            payload.month
            if payload.frequency_unit == TransactionFrequencyUnitEnum.YEAR
            else None
        )
        payload = payload.model_copy(
            update={"week_day": week_day, "day_of_month": day_of_month, "month": month}
        )
        return TransactionSeries(user_id=user_id, **payload.model_dump())

    async def resolve_open_series(
        self,
        *,
        user: User,
        name: str,
        account_id: UUID,
        direction: TransactionDirectionEnum,
    ) -> TransactionSeries | None:
        """Find the open series a confirmed recurrence belongs to.

        Matches on normalized name, account and direction. Closed series
        (installments) are never candidates, so same-named installment plans do
        not collide with a recurrence. Runs inside the caller's transaction and
        never opens its own, so the lookup and the write that follows stay
        atomic.
        """
        async with self._operation("resolve_open_series", user.username):
            target = to_snake_case(name)
            candidates = await self.repository.open_candidates(
                user_id=user.id, account_id=account_id, direction=direction
            )
            return next(
                (
                    candidate
                    for candidate in candidates
                    if to_snake_case(candidate.name) == target
                ),
                None,
            )
