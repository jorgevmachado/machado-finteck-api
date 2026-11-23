from __future__ import annotations

import logging
from uuid import UUID

from app.core.logging import LoggingParams
from app.core.service import BaseService

from app.domain.transaction.scheduled.repository import ScheduledTransactionRepository
from app.domain.transaction.scheduled.schema import ScheduledTransactionCreateSchema, ScheduledTransactionSchema, \
    ScheduledTransactionUpdateSchema, ScheduledTransactionRequestUpdateSchema
from app.models import ScheduledTransaction, TransactionStatusEnum, User
from app.shared.schemas import Message

logger = logging.getLogger(__name__)

class ScheduledTransactionService(
    BaseService[
        ScheduledTransaction,
        ScheduledTransactionCreateSchema,
        ScheduledTransactionUpdateSchema
    ]
):
    repository_class = ScheduledTransactionRepository

    def __init__(self, repository: ScheduledTransactionRepository) -> None:
        super().__init__(
            repository,
            alias="ScheduledTransaction",
            logger_params=LoggingParams(
                logger=logger,
                service="ScheduledTransactionService",
                operation="scheduled_transaction"
            ),
            schema_class=ScheduledTransactionSchema,
            cache_prefix="scheduled_transaction"
        )

    def _build_entity(self, user_id: UUID, data: dict[str, object]) -> ScheduledTransaction:
        status = data.get("status")
        settled_on = data.get("settled_on")
        if status == TransactionStatusEnum.SETTLED and not settled_on:
            raise ValueError("settled_on is required when status is SETTLED")
        payload = ScheduledTransactionCreateSchema.model_validate(data)

        if status != TransactionStatusEnum.SETTLED and settled_on:
            payload = payload.model_copy(update={"settled_on": None})

        return ScheduledTransaction(user_id=user_id, **payload.model_dump())

    async def delete_scheduled(self, user: User, identifier: UUID | str, transaction_series_id: UUID) -> Message:
        async with self._operation("delete", user.username, identifier):
            async with self.repository.transaction():
                entity = await self._find(
                    user_id=user.id,
                    filters={
                        "id": identifier,
                        "transaction_series_id": transaction_series_id
                    },
                    required=True
                )
                assert entity is not None
                await self.repository.delete(entity, user_id=user.id)
            await self._invalidate_cache(user, entity, "delete")
            return Message(message=f"Delete {self.alias} {identifier} successfully")

    async def update_scheduled(
            self,
            *,
            identifier: UUID | str,
            transaction_series_id: UUID,
            payload: ScheduledTransactionRequestUpdateSchema,
            user: User,
    ) -> Message:
        async with self._operation("update", user.username, identifier):
            async with self.repository.transaction():
                entity = await self._find(
                    user_id=user.id,
                    filters={
                        "id": identifier,
                        "transaction_series_id": transaction_series_id,
                    },
                    required=True,
                )
                assert entity is not None

                data = await self._prepare_update(
                    entity,
                    self._write_data(payload, partial=True),
                    user,
                )
                for field, value in data.items():
                    self.repository._column(field)
                    setattr(entity, field, value)

                await self.repository.update(entity, user_id=user.id)

            await self._invalidate_cache(user, entity, "update")
            return Message(
                message=f"Update {self.alias} {identifier} successfully"
            )