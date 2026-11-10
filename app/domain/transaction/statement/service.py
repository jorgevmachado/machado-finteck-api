import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import handle_service_exception
from app.core.logging import LoggingParams, log_service_success
from app.core.pagination import CustomLimitOffsetPage, is_paginate
from app.core.pagination.pagination import get_limit_offset_params
from app.domain.transaction.statement.business import combine_statement, project_series
from app.domain.transaction.statement.repository import StatementRepository
from app.domain.transaction.statement.schema import (
    StatementEntrySchema,
    StatementFilterSchema,
    StatementSeriesSchema,
)
from app.models import User

logger = logging.getLogger(__name__)


class StatementService:
    def __init__(self, repository: StatementRepository) -> None:
        self.repository = repository
        self.logger_params = LoggingParams(
            logger=logger, service="StatementService", operation="statement"
        )

    @classmethod
    def from_session(cls, session: AsyncSession) -> "StatementService":
        return cls(StatementRepository(session))

    async def list_all(
        self, *, user: User, page_filter: StatementFilterSchema
    ) -> list[StatementEntrySchema] | CustomLimitOffsetPage[StatementEntrySchema]:
        try:
            filters = page_filter
            series = await self.repository.series(user_id=user.id, filters=filters)
            projections = [
                entry
                for entity in series
                for entry in project_series(
                    StatementSeriesSchema.model_validate(entity), filters
                )
            ]
            ranges = {}
            for entry in projections:
                assert entry.transaction_serie is not None
                assert entry.occurrence_index is not None
                series_id = entry.transaction_serie.id
                first, _ = ranges.get(
                    series_id,
                    (entry.occurrence_index, entry.occurrence_index),
                )
                ranges[series_id] = (first, entry.occurrence_index)
            transactions = await self.repository.transactions(
                user_id=user.id, filters=filters
            )
            scheduled = await self.repository.scheduled(
                user_id=user.id, filters=filters, projected_ranges=ranges
            )
            entries = combine_statement(
                transactions=[
                    StatementEntrySchema.model_validate(entity)
                    for entity in transactions
                ],
                projections=projections,
                scheduled=[
                    StatementEntrySchema.model_validate(entity).model_copy(
                        update={
                            "source": "SCHEDULED",
                            "series_name": parent.name,
                            "series_kind": parent.kind,
                            "installments": parent.installments,
                        }
                    )
                    for entity, parent in scheduled
                ],
                filters=filters,
            )
            result: (
                list[StatementEntrySchema] | CustomLimitOffsetPage[StatementEntrySchema]
            ) = entries
            if is_paginate(page_filter):
                params = get_limit_offset_params(page_filter)
                result = CustomLimitOffsetPage[StatementEntrySchema].create(
                    entries[params.offset : params.offset + params.limit],
                    params=params,
                    total=len(entries),
                )
        except Exception as exception:
            handle_service_exception(
                exception,
                logger=logger,
                service="StatementService",
                operation="statement",
                user_request=user.username,
                raise_exception=True,
            )
        log_service_success(
            self.logger_params,
            message=f"Statement listed successfully: {len(entries)} entries",
            user_request=user.username,
        )
        return result
