from __future__ import annotations

import asyncio
import logging
from http import HTTPStatus
from uuid import UUID

from fastapi import HTTPException, UploadFile
from app.core.logging import LoggingParams
from app.core.pagination import CustomLimitOffsetPage
from app.domain.beneficiary.service import BeneficiaryService
from app.domain.category.service import CategoryService
from app.domain.institution.service import InstitutionService
from app.domain.payer.service import PayerService
from app.domain.transaction.scheduled.service import ScheduledTransactionService
from app.domain.transaction.series.schema import TransactionSeriesCreateSchema
from app.domain.transaction.series.service import TransactionSeriesService
from app.domain.transaction.service import TransactionService
from app.domain.receipt.data.schema import ReceiptData
from app.domain.receipt.extraction.service import ExtractionService
from app.domain.receipt.file.file import (
    validate_file,
    calculate_hash,
    validate_batch_size,
)
from app.domain.receipt.interpretation import Interpretation, Converter
from app.domain.receipt.interpretation.schema import InterpretationResult
from app.domain.receipt.payment.schema import PaymentCreateSchema
from app.domain.receipt.payment.service import PaymentService
from app.domain.receipt.repository import ReceiptRepository
from app.domain.receipt.confirm_schema import (
    ReceiptConfirmConflictSchema,
    ReceiptConfirmOutcome,
)
from app.domain.receipt.rules.schema import ReceiptRulesFilter
from app.domain.receipt.rules.service import ReceiptRulesService
from app.domain.receipt.schema import (
    ReceiptUploadSchema,
    BatchReceiptSchema,
    ReceiptConfirmSchema,
    ReceiptCreateSchema,
    ReceiptUpdateSchema,
)
from app.domain.transaction.scheduled.schema import ScheduledTransactionCreateSchema
from app.domain.transaction.schema import TransactionCreateSchema
from app.domain.transaction.statement.business import (
    occurrence_index_at,
    shift_occurrences_back,
)
from app.models import (
    Payment,
    Receipt,
    ReceiptStatusEnum,
    ScheduledTransaction,
    TransactionKindEnum,
    TransactionSeries,
    TransactionStatusEnum,
    TransactionFrequencyUnitEnum,
    User,
)
from app.core.service import BaseService

logger = logging.getLogger(__name__)


class ReceiptService(BaseService[Receipt, ReceiptCreateSchema]):
    repository_class = ReceiptRepository
    repository: ReceiptRepository

    def __init__(self, repository: ReceiptRepository):
        super().__init__(
            repository,
            alias="Receipt",
            logger_params=LoggingParams(
                logger=logger, service="ReceiptService", operation="receipt"
            ),
        )
        self.extraction_service = ExtractionService()
        self.rules_service = ReceiptRulesService.from_session(repository.session)
        self.payment_service = PaymentService.from_session(repository.session)
        self.payer_service = PayerService.from_session(repository.session)
        self.beneficiary_service = BeneficiaryService.from_session(repository.session)
        self.institution_service = InstitutionService.from_session(repository.session)
        self.category_service = CategoryService.from_session(repository.session)
        self.transaction_service = TransactionService.from_session(repository.session)
        self.series_service = TransactionSeriesService.from_session(repository.session)
        self.scheduled_service = ScheduledTransactionService.from_session(
            repository.session
        )

    def _build_entity(self, user_id: UUID, data: dict[str, object]) -> Receipt:
        payload = ReceiptCreateSchema.model_validate(data)
        return Receipt(user_id=user_id, **payload.model_dump())

    async def find_one(self, receipt_id: UUID | str, user: User) -> Receipt:
        return await super().find_one(receipt_id, user)

    async def find_by_hash(self, user: User, file_hash: str) -> Receipt | None:
        user_id, username = user.id, user.username
        async with self._operation("find_by", username, None):
            return await self._find(
                filters={"file_hash": file_hash}, user_id=user_id, required=False
            )

    async def _interpret_receipt(self, text: str, user: User) -> InterpretationResult:
        result = await self.rules_service.list_profiles(
            ReceiptRulesFilter.model_validate({"is_active": True, "limit": None}),
            user,
        )
        rules = result.items if isinstance(result, CustomLimitOffsetPage) else result
        for profile in rules:
            profile.identification_rules = [
                rule for rule in profile.identification_rules if rule.is_active
            ]
            profile.field_rules = [
                rule for rule in profile.field_rules if rule.is_active
            ]
        interpretation = await asyncio.to_thread(Interpretation, rules, text)
        return await asyncio.to_thread(interpretation.result)

    async def persist_upload(
        self,
        user: User,
        file_size: int,
        file_hash: str,
        interpretation: InterpretationResult,
        receipt: Receipt | None = None,
        file_name: str | None = None,
        content_type: str | None = None,
    ) -> Receipt:
        user_id, username = user.id, user.username
        async with self._operation("persist_upload", username):
            status = (
                ReceiptStatusEnum.RECEIVED
                if not interpretation.errors
                else ReceiptStatusEnum.FAILED
            )
            interpretation_data = interpretation.data.model_dump(mode="json")
            if receipt:
                async with self.repository.transaction():
                    if file_name:
                        receipt.file_name = file_name
                    if content_type:
                        receipt.file_type = content_type
                    receipt.file_size = file_size
                    receipt.data = interpretation_data
                    receipt.status = status
                    return await self.repository.save(entity=receipt, user_id=user_id)
            async with self.repository.transaction():
                return await self.repository.save(
                    user_id=user_id,
                    entity=self._build_entity(
                        user_id,
                        {
                            "data": interpretation_data,
                            "status": status,
                            "file_hash": file_hash,
                            "file_name": file_name,
                            "file_type": content_type,
                            "file_size": file_size,
                        },
                    ),
                )

    async def upload(self, file: UploadFile, user: User) -> ReceiptUploadSchema:
        username = user.username
        async with self._operation("upload", username):
            content = await validate_file(file)
            file_hash = calculate_hash(content)
            receipt = await self.find_by_hash(user=user, file_hash=file_hash)

            if receipt and (
                receipt.status == ReceiptStatusEnum.RECEIVED
                or receipt.status == ReceiptStatusEnum.PROCESSED
            ):
                return ReceiptUploadSchema(
                    id=receipt.id,
                    data=ReceiptData.model_validate(receipt.data)
                    if receipt.data is not None
                    else None,
                    status=ReceiptStatusEnum.FAILED,
                    errors=[],
                    file_name=receipt.file_name,
                    file_type=receipt.file_type,
                    file_size=receipt.file_size,
                    error_message="Receipt has already been received or processed",
                )

            text = await self.extraction_service.extract(
                content=content, content_type=file.content_type
            )
            interpretation = await self._interpret_receipt(text, user)
            file_size = len(content)

            entity = await self.persist_upload(
                user=user,
                receipt=receipt,
                file_size=file_size,
                file_hash=file_hash,
                file_name=file.filename,
                content_type=file.content_type,
                interpretation=interpretation,
            )
            return ReceiptUploadSchema(
                id=entity.id,
                data=interpretation.data,
                status=entity.status,
                errors=interpretation.errors,
                file_name=entity.file_name,
                file_type=entity.file_type,
                file_size=entity.file_size,
                error_message=None,
            )

    async def batch(self, files: list[UploadFile], user: User) -> BatchReceiptSchema:
        validate_batch_size(files)
        items: list[ReceiptUploadSchema] = []
        for file in files:
            try:
                item = await self.upload(file=file, user=user)
                items.append(item)
            except Exception as exception:
                items.append(
                    ReceiptUploadSchema(
                        id=UUID(int=0),
                        data=None,
                        errors=[],
                        file_name=file.filename,
                        file_type=file.content_type,
                        file_size=0,
                        error_message=str(exception),
                        status=ReceiptStatusEnum.FAILED,
                    )
                )
        failed = sum(item.status == ReceiptStatusEnum.FAILED for item in items)
        received = sum(item.status == ReceiptStatusEnum.RECEIVED for item in items)
        processed = sum(item.status == ReceiptStatusEnum.PROCESSED for item in items)
        processing = sum(item.status == ReceiptStatusEnum.PROCESSING for item in items)

        return BatchReceiptSchema(
            total=len(items),
            items=items,
            failed=failed,
            received=received,
            processed=processed,
            processing=processing,
        )

    async def validate_confirm_receipt(self, receipt_id: UUID, user: User) -> Receipt:
        username = user.username
        async with self._operation("validate_confirm_receipt", username):
            receipt = await self.find_one(receipt_id=receipt_id, user=user)
            if receipt.status != ReceiptStatusEnum.RECEIVED:
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT,
                    detail="Receipt is not ready for confirmation",
                )
            return receipt

    async def validate_update_receipt(self, receipt_id: UUID, user: User) -> Receipt:
        username = user.username
        async with self._operation("validate_update_receipt", username, receipt_id):
            receipt = await self.find_one(receipt_id=receipt_id, user=user)
            if receipt.status in (
                ReceiptStatusEnum.PROCESSED,
                ReceiptStatusEnum.PROCESSING,
            ):
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT,
                    detail="Receipt is processed or in processing and cannot be updated",
                )
            return receipt

    async def confirm(
        self, receipt_id: UUID, user: User, payload: ReceiptConfirmSchema
    ) -> ReceiptConfirmOutcome:
        username = user.username
        async with self._operation("confirm", username):
            receipt = await self.validate_confirm_receipt(receipt_id, user)
            await self.payment_service.check_receipt(receipt_id, user)
            payer = await self.payer_service.resolve(user=user, name=payload.payer)
            beneficiary = await self.beneficiary_service.resolve(
                user=user, name=payload.beneficiary
            )
            source_institution = await self.institution_service.resolve(
                user=user, name=payload.source_institution
            )
            subcategory = await self.category_service.find_subcategory_by_id(
                subcategory_id=payload.subcategory_id, user_id=user.id
            )
            destination_institution = (
                await self.institution_service.resolve(
                    user=user, name=payload.destination_institution
                )
                if payload.destination_institution
                else None
            )

            async with self.repository.transaction():
                payment = await self.payment_service.add_owned(
                    user,
                    PaymentCreateSchema(
                        payer_id=payer.id,
                        receipt_id=receipt.id,
                        amount=payload.paid_amount,
                        payment_date=payload.payment_date,
                        beneficiary_id=beneficiary.id,
                        subcategory_id=subcategory.id,
                        source_institution_id=source_institution.id,
                        description=payload.description,
                        destination_institution_id=destination_institution.id
                        if destination_institution
                        else None,
                    ),
                )
                result = await self._write_entry(
                    user=user,
                    payload=payload,
                    payment=payment,
                    subcategory_id=subcategory.id,
                )
                receipt.status = ReceiptStatusEnum.PROCESSED
                await self.repository.save(entity=receipt, user_id=user.id)

            await self._invalidate_entry_caches(user, result)
            return result

    async def _invalidate_entry_caches(
        self, user: User, result: ReceiptConfirmOutcome
    ) -> None:
        """Drop cached reads only after the transaction has committed.

        `payment` has no cache; transaction, series and occurrence do. Invalidating
        inside the transaction would let a concurrent read repopulate the cache
        with the pre-commit state.
        """
        if result.transaction is not None:
            await self.transaction_service._invalidate_cache(
                user, result.transaction, "confirm"
            )
        if result.series is not None:
            await self.series_service._invalidate_cache(user, result.series, "confirm")
        if result.occurrence is not None:
            await self.scheduled_service._invalidate_cache(
                user, result.occurrence, "confirm"
            )

    async def _write_entry(
        self,
        *,
        user: User,
        payload: ReceiptConfirmSchema,
        payment: Payment,
        subcategory_id: UUID,
    ) -> ReceiptConfirmOutcome:
        """Write the financial entry that represents the confirmed payment.

        Runs inside the caller's transaction. `SIMPLE` writes a `Transaction`;
        `INSTALLMENT` and `RECURRING` attach a settled occurrence (override) to a
        series, which is the only mechanism that suppresses the projection of
        that date in the statement.
        """
        if payload.transaction_kind == "SIMPLE":
            transaction = await self.transaction_service.add_owned(
                user,
                TransactionCreateSchema(
                    name=payload.name,
                    note=payload.note,
                    value=payload.paid_amount,
                    status=TransactionStatusEnum.SETTLED,
                    direction=payload.direction,
                    settled_on=payload.payment_date,
                    account_id=payload.account_id,
                    expected_on=payload.expected_on or payload.payment_date,
                    credit_card_id=payload.credit_card_id,
                    subcategory_id=subcategory_id,
                    receipt_payment_id=payment.id,
                ),
            )
            return ReceiptConfirmOutcome(payment=payment, transaction=transaction)

        series = await self._resolve_series(
            user=user, payload=payload, subcategory_id=subcategory_id
        )
        occurrence = await self._write_occurrence(
            user=user,
            payload=payload,
            payment=payment,
            series=series,
            subcategory_id=subcategory_id,
        )
        return ReceiptConfirmOutcome(
            payment=payment, series=series, occurrence=occurrence
        )

    async def _write_occurrence(
        self,
        *,
        user: User,
        payload: ReceiptConfirmSchema,
        payment: Payment,
        series: TransactionSeries,
        subcategory_id: UUID,
    ) -> ScheduledTransaction:
        """Attach the paid occurrence to the series, overwriting on consent."""
        occurrence_on = payload.expected_on or payload.payment_date
        index = (
            payload.installment_index
            if payload.transaction_kind == "INSTALLMENT"
            else occurrence_index_at(series, occurrence_on)
        )
        if index is None:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_CONTENT,
                detail="The occurrence date is not part of the series",
            )

        existing = await self.scheduled_service.find_by(
            user=user,
            filters={
                "transaction_series_id": series.id,
                "occurrence_index": index,
            },
            required=False,
        )
        if existing is not None:
            if not payload.overwrite:
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT,
                    detail=ReceiptConfirmConflictSchema(
                        type="OCCURRENCE_EXISTS",
                        existing={
                            "id": str(existing.id),
                            "settled_on": existing.settled_on.isoformat()
                            if existing.settled_on
                            else None,
                            "value": str(existing.value),
                        },
                        occurrence={
                            "transaction_series_id": str(series.id),
                            "occurrence_index": index,
                            "occurrence_on": occurrence_on.isoformat(),
                        },
                    ).model_dump(mode="json"),
                )
            await self.scheduled_service.delete_occurrence(
                user=user, occurrence=existing
            )

        return await self.scheduled_service.add_owned(
            user,
            ScheduledTransactionCreateSchema(
                transaction_series_id=series.id,
                name=payload.name,
                note=payload.note,
                value=payload.paid_amount,
                status=TransactionStatusEnum.SETTLED,
                direction=payload.direction,
                settled_on=payload.payment_date,
                account_id=payload.account_id,
                expected_on=occurrence_on,
                occurrence_on=occurrence_on,
                occurrence_index=index,
                credit_card_id=payload.credit_card_id,
                subcategory_id=subcategory_id,
                receipt_payment_id=payment.id,
            ),
        )

    async def _resolve_series(
        self,
        *,
        user: User,
        payload: ReceiptConfirmSchema,
        subcategory_id: UUID,
    ) -> TransactionSeries:
        """Reuse the matching open series for a recurrence, or create the plan."""
        if payload.transaction_kind == "RECURRING":
            existing = await self.series_service.resolve_open_series(
                user=user,
                name=payload.name,
                account_id=payload.account_id,
                direction=payload.direction,
            )
            if existing is not None:
                return existing
            return await self.series_service.add_owned(
                user,
                TransactionSeriesCreateSchema(
                    kind=TransactionKindEnum.OPEN,
                    name=payload.name,
                    note=payload.note,
                    value=payload.paid_amount,
                    direction=payload.direction,
                    start_date=payload.expected_on or payload.payment_date,
                    account_id=payload.account_id,
                    credit_card_id=payload.credit_card_id,
                    subcategory_id=subcategory_id,
                    frequency_unit=payload.frequency_unit,
                    frequency_interval=payload.frequency_interval,
                ),
            )

        assert payload.installment_index is not None
        assert payload.installments_total is not None
        unit = payload.frequency_unit or TransactionFrequencyUnitEnum.MONTH
        interval = payload.frequency_interval or 1
        occurrence_on = payload.expected_on or payload.payment_date
        return await self.series_service.add_owned(
            user,
            TransactionSeriesCreateSchema(
                kind=TransactionKindEnum.CLOSED,
                name=payload.name,
                note=payload.note,
                value=payload.paid_amount,
                direction=payload.direction,
                start_date=shift_occurrences_back(
                    occurrence_on,
                    steps=payload.installment_index - 1,
                    unit=unit,
                    interval=interval,
                ),
                end_date=None,
                account_id=payload.account_id,
                credit_card_id=payload.credit_card_id,
                subcategory_id=subcategory_id,
                installments=payload.installments_total,
                frequency_unit=unit,
                frequency_interval=interval,
            ),
        )

    async def update_receipt(
        self, receipt_id: UUID, user: User, payload: ReceiptUpdateSchema
    ) -> Receipt:
        username = user.username
        async with self._operation("update_receipt", username, receipt_id):
            receipt = await self.validate_update_receipt(receipt_id, user)
            await self.payment_service.check_receipt(receipt_id, user)

            converter = await asyncio.to_thread(
                Converter, payload.model_dump(mode="json")
            )
            validated = await asyncio.to_thread(converter.result)

            async with self.repository.transaction():
                receipt.data = validated.data.model_dump(mode="json")
                receipt.status = (
                    ReceiptStatusEnum.RECEIVED
                    if not validated.errors
                    else ReceiptStatusEnum.FAILED
                )

                return await self.repository.save(entity=receipt, user_id=user.id)
