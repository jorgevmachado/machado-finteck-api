from __future__ import annotations

import logging
from http import HTTPStatus
from secrets import randbits
from uuid import UUID

from fastapi import HTTPException

from app.core.logging import LoggingParams
from app.core.service import BaseService

from app.domain.transaction.business import build_transaction_seed
from app.domain.transaction.repository import TransactionRepository
from app.domain.transaction.schema import (
    TransactionCreateSchema,
    TransactionSchema,
    TransactionUpdateSchema,
    TransactionSeedRequestSchema,
    TransactionSeedSchema,
)
from app.domain.transaction.seeds import (
    load_seeds_transactions,
    load_seeds_recurrences,
    load_seeds_installment_plans,
)
from app.domain.transaction.scheduled.service import ScheduledTransactionService
from app.domain.transaction.series.service import TransactionSeriesService
from app.models import (
    ScheduledTransaction,
    Transaction,
    TransactionSeries,
    TransactionStatusEnum,
    User,
    utcnow,
)

logger = logging.getLogger(__name__)


class TransactionService(
    BaseService[Transaction, TransactionCreateSchema, TransactionUpdateSchema]
):
    repository_class = TransactionRepository
    repository: TransactionRepository

    def __init__(self, repository: TransactionRepository) -> None:
        super().__init__(
            repository,
            alias="Transaction",
            logger_params=LoggingParams(
                logger=logger, service="TransactionService", operation="transaction"
            ),
            schema_class=TransactionSchema,
            cache_prefix="transaction",
        )

    def _build_entity(self, user_id: UUID, data: dict[str, object]) -> Transaction:
        status = data.get("status")
        settled_on = data.get("settled_on")
        if status == TransactionStatusEnum.SETTLED and not settled_on:
            raise ValueError("settled_on is required when status is SETTLED")
        payload = TransactionCreateSchema.model_validate(data)

        if status != TransactionStatusEnum.SETTLED and settled_on:
            payload = payload.model_copy(update={"settled_on": None})

        return Transaction(user_id=user_id, **payload.model_dump())

    async def seed(
        self, *, user: User, payload: TransactionSeedRequestSchema
    ) -> TransactionSeedSchema:
        async with self._operation("seed", user.username):
            if (
                user.role is None
                or user.role.name_code != "admin"
                or user.role.deleted_at is not None
            ):
                raise HTTPException(
                    status_code=HTTPStatus.FORBIDDEN,
                    detail="Only administrators can seed transactions",
                )
            seed = payload.seed if payload.seed is not None else randbits(32)
            async with self.repository.transaction():
                accounts = await self.repository.seed_account_ids(user_id=user.id)
                if not accounts:
                    raise HTTPException(
                        status_code=HTTPStatus.CONFLICT,
                        detail="At least one active account is required to seed transactions",
                    )
                plan = build_transaction_seed(
                    payload=payload,
                    seed=seed,
                    today=utcnow().date(),
                    templates=load_seeds_transactions(),
                    recurrence_templates=load_seeds_recurrences(),
                    installment_templates=load_seeds_installment_plans(),
                    account_ids=accounts,
                    credit_card_ids=await self.repository.seed_credit_card_ids(
                        user_id=user.id
                    ),
                    subcategories=await self.repository.seed_subcategories(
                        user_id=user.id
                    ),
                )
                transactions = [
                    self._build_entity(user.id, item.model_dump())
                    for item in plan.transactions
                ]
                series = []
                for item in plan.series:
                    entity = TransactionSeries(
                        user_id=user.id, **item.series.model_dump()
                    )
                    entity.scheduled_transactions = [
                        ScheduledTransaction(
                            user_id=user.id,
                            transaction_series_id=entity.id,
                            **occurrence.model_dump(),
                        )
                        for occurrence in item.occurrences
                    ]
                    series.append(entity)
                await self.repository.save_seed(
                    transactions=transactions, series=series, user_id=user.id
                )
            if transactions:
                await self._invalidate_cache(user, transactions[0], "seed")
            if series:
                series_service = TransactionSeriesService.from_session(
                    self.repository.session
                )
                scheduled_service = ScheduledTransactionService.from_session(
                    self.repository.session
                )
                await series_service._invalidate_cache(user, series[0], "seed")
                await scheduled_service._invalidate_cache(
                    user, series[0].scheduled_transactions[0], "seed"
                )
            return TransactionSeedSchema(
                seed=seed,
                start_date=plan.start_date,
                end_date=plan.end_date,
                transactions=len(transactions),
                transaction_series=len(series),
                scheduled_transactions=sum(
                    len(item.occurrences) for item in plan.series
                ),
            )
