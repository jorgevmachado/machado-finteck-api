from __future__ import annotations

import logging
from uuid import UUID

from app.core.logging import LoggingParams
from app.core.service import BaseService

from app.domain.transaction.series.repository import TransactionSeriesRepository
from app.domain.transaction.series.schema import TransactionSeriesCreateSchema, TransactionSeriesSchema, TransactionSeriesUpdateSchema
from app.models import TransactionSeries, TransactionFrequencyUnitEnum

logger = logging.getLogger(__name__)

class TransactionSeriesService(
    BaseService[
        TransactionSeries,
        TransactionSeriesCreateSchema,
        TransactionSeriesUpdateSchema
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
                operation="transaction_series"
            ),
            schema_class=TransactionSeriesSchema,
            cache_prefix="transaction_series"
        )

    def _build_entity(self, user_id: UUID, data: dict[str, object]) -> TransactionSeries:
        payload = TransactionSeriesCreateSchema.model_validate(data)
        week_day = payload.week_day if payload.frequency_unit == TransactionFrequencyUnitEnum.WEEK else None
        day_of_month = payload.day_of_month if payload.frequency_unit != TransactionFrequencyUnitEnum.WEEK else None
        month = payload.month if payload.frequency_unit == TransactionFrequencyUnitEnum.YEAR else None
        payload = payload.model_copy(update={"week_day": week_day, "day_of_month": day_of_month, "month": month})
        return TransactionSeries(user_id=user_id, **payload.model_dump())