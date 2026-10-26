from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from http import HTTPStatus
from typing import AsyncIterator
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import handle_service_exception
from app.core.logging import LoggingParams, log_service_success
from app.core.pagination import CustomLimitOffsetPage

from app.domain.receipt.payment.repository import PaymentRepository
from app.models import User, Payment
from app.shared.schemas import FilterPage

logger = logging.getLogger(__name__)

class PaymentService:
    def __init__(self, repository: PaymentRepository):
        self.alias = "Payment"
        self.repository = repository
        self.logger_params = LoggingParams(
            logger=logger, service="PaymentService", operation="payment"
        )

    @classmethod
    def from_session(cls, session: AsyncSession) -> PaymentService:
        return cls(PaymentRepository(session))

    @asynccontextmanager
    async def _operation(
            self, operation: str, user_request: str, target_id: UUID | None = None
    ) -> AsyncIterator[None]:
        try:
            yield
        except Exception as exception:
            handle_service_exception(
                exception,
                logger=logger,
                service=self.logger_params.service,
                operation=operation,
                user_request=user_request,
                raise_exception=True,
            )
        else:
            log_service_success(
                self.logger_params,
                operation=operation,
                message=(f"Receipt Payment {operation} successfully: {target_id}"),
                user_request=user_request,
            )

    async def list_all(
        self, page_filter: FilterPage, user: User
    ) -> list[Payment] | CustomLimitOffsetPage[Payment]:
        async with self._operation("list_all", user.username):
            return await self.repository.list_all(
                page_filter=page_filter.with_updates(user_id=user.id)
            )

    async def find_one(self, payment_id: UUID, user: User) -> Payment:
        async with self._operation("find_one", user.username, payment_id):
            payment = await self.repository.find_by(id=payment_id, user_id=user.id)
            if payment is None:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND, detail="Payment not found"
                )
            return payment

    async def find_by(self, user: User, receipt_id: UUID) -> Payment | None:
        user_id, username = user.id, user.username
        async with self._operation("find_by", username, None):
            return await self.repository.find_by(receipt_id=receipt_id, user_id=user_id)

    async def check_receipt(self, receipt_id: UUID, user: User) -> None:
        user_id, username = user.id, user.username
        async with self._operation("check_receipt", username, None):
            payment = await self.repository.find_by(receipt_id=receipt_id, user_id=user_id)
            if payment is not None:
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT,
                    detail="Receipt already has a payment",
                )

    async def create(
            self,
            user: User,
            payer_id: UUID,
            receipt_id: UUID,
            amount: Decimal,
            payment_date: date,
            beneficiary_id: UUID,
            subcategory_id: UUID,
            source_institution_id: UUID,
            description: str | None,
            destination_institution_id: UUID | None,
    ) -> Payment:
        user_id, username = user.id, user.username
        async with self._operation("create", username, None):
            return await self.repository.save(entity=Payment(
                user_id=user_id,
                payer_id=payer_id,
                receipt_id=receipt_id,
                amount=amount,
                payment_date=payment_date,
                beneficiary_id=beneficiary_id,
                subcategory_id=subcategory_id,
                source_institution_id=source_institution_id,
                description=description,
                destination_institution_id=destination_institution_id
            ))