from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import handle_service_exception
from app.core.logging import LoggingParams, log_service_success
from app.core.pagination import CustomLimitOffsetPage
from app.domain.receipt.extraction.service import ExtractionService
from app.domain.receipt.file.file import validate_file, calculate_hash
from app.domain.receipt.interpretation import Interpretation
from app.domain.receipt.interpretation.schema import InterpretationResult
from app.domain.receipt.rules.schema import ReceiptRulesFilter
from app.domain.receipt.rules.service import ReceiptRulesService
from app.domain.receipt.schema import ReceiptUploadSchema
from app.models import User

logger = logging.getLogger(__name__)


class ReceiptService:
    def __init__(self, repository: AsyncSession):
        self.alias = "Receipt"
        self.repository = repository
        self.logger_params = LoggingParams(
            logger=logger, service="ReceiptService", operation="receipt"
        )
        self.extraction_service = ExtractionService()
        self.rules_service = ReceiptRulesService.from_session(repository)

    @classmethod
    def from_session(cls, session):
        return cls(session)

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

    async def find_by(self, user: User, file_hash: str):
        username = user.username
        async with self._operation("find_by", username, None):
            pass
        return

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

    async def upload_receipt(self, file: UploadFile, user: User) -> ReceiptUploadSchema:
        user_id, username = user.id, user.username
        async with self._operation("upload_receipt", username):
            content = await validate_file(file)
            file_hash = calculate_hash(content)
            text = await self.extraction_service.extract(
                content=content, content_type=file.content_type
            )
            interpretation = await self._interpret_receipt(text, user)
            return ReceiptUploadSchema(
                filename=file.filename,
                user_id=user_id,
                status="processed",
                file_hash=file_hash,
                data=interpretation.data,
                errors=interpretation.errors,
            )
