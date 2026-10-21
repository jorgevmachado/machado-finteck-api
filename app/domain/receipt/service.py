from __future__ import annotations

import logging
from http import HTTPStatus
from uuid import UUID

from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache.service import CacheService
from app.core.exceptions import handle_service_exception
from app.core.logging import LoggingParams, log_service_success
from app.domain.receipt.data.schema import ReceiptData
from app.domain.receipt.extraction.service import ExtractionService
from app.domain.receipt.file.validation import (
    validate_file,
    calculate_hash,
    validate_batch_size,
)
from app.domain.receipt.interpretation.schema import InterpretationResult
from app.domain.receipt.interpretation.configured_service import (
    ConfiguredInterpretationService,
)
from app.domain.receipt.repository import ReceiptRepository
from app.domain.receipt.schema import (
    ReceiptSchema,
    UploadReceiptSchema,
    BatchReceiptSchema,
)
from app.models import User, Receipt, ReceiptStatusEnum

logger = logging.getLogger(__name__)


class ReceiptService:
    def __init__(self, repository: ReceiptRepository) -> None:
        self.alias = "Receipt"
        self.repository = repository
        self.logger_params = LoggingParams(
            logger=logger, service="ReceiptService", operation="receipt"
        )
        self.cache_service = CacheService(
            alias=self.alias,
            prefix="receipt",
            logger_params=self.logger_params,
            schema_class=ReceiptSchema,
        )
        self.extraction_service = ExtractionService()
        self.interpretation_service = ConfiguredInterpretationService(
            repository.session
        )

    @classmethod
    def from_session(cls, session: AsyncSession) -> ReceiptService:
        return cls(ReceiptRepository(session))

    async def find_by(
        self,
        *,
        user_id: UUID,
        id: UUID | None = None,
        file_hash: str | None = None,
        user_request: str | None = None,
        without_throw: bool = False,
    ) -> Receipt | None:
        try:
            result = await self.repository.find_by(
                id=id, file_hash=file_hash, user_id=user_id
            )
            if result is None and not without_throw:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND, detail="Receipt not found"
                )
            log_service_success(
                self.logger_params,
                operation="find_by",
                message=f"Find by {self.alias} successfully",
                user_request=user_request,
            )
            return result
        except Exception as exception:
            handle_service_exception(
                exception,
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="find_by",
                user_request=user_request,
                raise_exception=True,
            )

    async def persist_upload(
        self,
        user_id: UUID,
        file_size: int,
        file_hash: str,
        interpretation: InterpretationResult,
        receipt: Receipt | None = None,
        file_name: str | None = None,
        content_type: str | None = None,
    ) -> Receipt:
        try:
            status = (
                ReceiptStatusEnum.RECEIVED
                if not interpretation.errors
                else ReceiptStatusEnum.FAILED
            )
            interpretation_data = interpretation.data.model_dump(mode="json")
            if interpretation.configuration is not None:
                interpretation_data["_interpretation"] = (
                    interpretation.configuration.model_dump(mode="json")
                )
            if receipt:
                receipt.file_size = file_size
                receipt.file_hash = file_hash
                receipt.data = interpretation_data
                receipt.status = status
                if file_name:
                    receipt.file_name = file_name
                if content_type:
                    receipt.file_type = content_type
                return await self.repository.save(entity=receipt)
            return await self.repository.save(
                entity=Receipt(
                    user_id=user_id,
                    file_hash=file_hash,
                    file_name=file_name,
                    file_type=content_type,
                    file_size=file_size,
                    data=interpretation_data,
                    status=status,
                )
            )
        except Exception as exception:
            handle_service_exception(
                exception,
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="persist_upload",
                raise_exception=True,
            )

    async def upload(self, file: UploadFile, user: User) -> UploadReceiptSchema:
        try:
            content = await validate_file(file)
            file_hash = calculate_hash(content)
            receipt = await self.find_by(
                user_id=user.id, file_hash=file_hash, without_throw=True
            )

            if receipt and (
                receipt.status == ReceiptStatusEnum.RECEIVED
                or receipt.status == ReceiptStatusEnum.PROCESSED
            ):
                return UploadReceiptSchema(
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

            extracted_text = await self.extraction_service.extract(
                content, file.content_type
            )
            interpretation = await self.interpretation_service.interpret(
                extracted_text, user_id=user.id
            )

            file_size = len(content)
            entity = await self.persist_upload(
                user_id=user.id,
                file_size=file_size,
                file_hash=file_hash,
                interpretation=interpretation,
                receipt=receipt,
                file_name=file.filename,
                content_type=file.content_type,
            )
            return UploadReceiptSchema(
                id=entity.id,
                data=interpretation.data,
                status=entity.status,
                errors=interpretation.errors,
                file_name=entity.file_name,
                file_type=entity.file_type,
                file_size=entity.file_size,
                error_message=None,
            )

        except Exception as exception:
            handle_service_exception(
                exception,
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="upload",
                user_request=user.username,
                raise_exception=True,
            )

    async def batch(self, files: list[UploadFile], user: User) -> BatchReceiptSchema:
        validate_batch_size(files)
        items: list[UploadReceiptSchema] = []
        for file in files:
            try:
                item = await self.upload(file=file, user=user)
                items.append(item)
            except Exception as exception:
                items.append(
                    UploadReceiptSchema(
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
