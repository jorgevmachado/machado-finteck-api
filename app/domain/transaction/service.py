from __future__ import annotations

import logging
from uuid import UUID

from app.core.logging import LoggingParams
from app.core.service import BaseService

from app.domain.transaction.repository import TransactionRepository
from app.domain.transaction.schema import TransactionCreateSchema, TransactionSchema, TransactionUpdateSchema
from app.models import Transaction

logger = logging.getLogger(__name__)

class TransactionService(
    BaseService[
        Transaction,
        TransactionCreateSchema,
        TransactionUpdateSchema
    ]
):
    repository_class = TransactionRepository

    def __init__(self, repository: TransactionRepository) -> None:
        super().__init__(
            repository,
            alias="Transaction",
            logger_params=LoggingParams(
                logger=logger,
                service="TransactionService",
                operation="transaction"
            ),
            schema_class=TransactionSchema,
            cache_prefix="transaction"
        )

    def _build_entity(self, user_id: UUID, data: dict[str, object]) -> Transaction:
        payload = TransactionCreateSchema.model_validate(data)
        return Transaction(user_id=user_id, **payload.model_dump())