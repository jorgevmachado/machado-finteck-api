from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import UUID

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import handle_service_exception
from app.core.logging import LoggingParams, log_service_success
from app.core.pagination import CustomLimitOffsetPage
from app.domain.receipt.data.schema import ReceiptData
from app.domain.receipt.extraction.service import ExtractionService
from app.domain.receipt.file.file import (
    validate_file,
    calculate_hash,
    validate_batch_size,
)
from app.domain.receipt.interpretation import Interpretation
from app.domain.receipt.interpretation.schema import InterpretationResult
from app.domain.receipt.repository import ReceiptRepository
from app.domain.receipt.rules.schema import ReceiptRulesFilter
from app.domain.receipt.rules.service import ReceiptRulesService
from app.domain.receipt.schema import ReceiptUploadSchema, BatchReceiptSchema
from app.models import User, Receipt, ReceiptStatusEnum
from app.shared.schemas import FilterPage

logger = logging.getLogger(__name__)


class ReceiptService:
    def __init__(self, repository: ReceiptRepository):
        self.alias = "Receipt"
        self.repository = repository
        self.logger_params = LoggingParams(
            logger=logger, service="ReceiptService", operation="receipt"
        )
        self.extraction_service = ExtractionService()
        self.rules_service = ReceiptRulesService.from_session(repository.session)

    @classmethod
    def from_session(cls, session: AsyncSession) -> ReceiptService:
        return cls(ReceiptRepository(session))

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
                message=(f"Receipt {operation} successfully: {target_id}"),
                user_request=user_request,
            )

    async def list_all(
        self, page_filter: FilterPage, user: User
    ) -> list[Receipt] | CustomLimitOffsetPage[Receipt]:
        async with self._operation("list_all", user.username):
            return await self.repository.list_all(
                page_filter=page_filter.with_updates(user_id=user.id)
            )

    async def find_one(self, receipt_id: UUID, user: User) -> Receipt:
        async with self._operation("find_one", user.username, receipt_id):
            receipt = await self.repository.find_by(id=receipt_id, user_id=user.id)
            if receipt is None:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND, detail="Receipt not found"
                )
            return receipt

    async def find_by(self, user: User, file_hash: str) -> Receipt | None:
        user_id, username = user.id, user.username
        async with self._operation("find_by", username, None):
            return await self.repository.find_by(file_hash=file_hash, user_id=user_id)

    async def _interpret_receipt(self, text: str, user: User) -> InterpretationResult:
        result = await self.rules_service.list_all(
            ReceiptRulesFilter(is_active=True, limit=None),
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
                if file_name:
                    receipt.file_name = file_name
                if content_type:
                    receipt.file_type = content_type
                receipt.file_size = file_size
                receipt.data = interpretation_data
                receipt.status = status
                return await self.repository.save(entity=receipt)
            return await self.repository.save(
                entity=Receipt(
                    data=interpretation_data,
                    status=status,
                    user_id=user_id,
                    file_hash=file_hash,
                    file_name=file_name,
                    file_type=content_type,
                    file_size=file_size,
                )
            )

    async def upload(self, file: UploadFile, user: User) -> ReceiptUploadSchema:
        username = user.username
        async with self._operation("upload", username):
            content = await validate_file(file)
            file_hash = calculate_hash(content)
            receipt = await self.find_by(user=user, file_hash=file_hash)

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