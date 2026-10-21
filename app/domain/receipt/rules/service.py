from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import handle_service_exception
from app.core.logging import LoggingParams, log_service_success

from app.core.cache.service import CacheService
from app.core.pagination import CustomLimitOffsetPage
from app.domain.account.schema import (
    AccountSchema,
)
from app.domain.receipt.rules.business import (
    ProfileReconciliationError,
    build_reconciliation_plan,
)
from app.domain.receipt.rules.defaults import load_default_receipt_rules
from app.domain.receipt.rules.configuration.engine import (
    SourceExtractionResult,
    extract_source,
)
from app.domain.receipt.rules.field.schema import ReceiptFieldRuleCreateSchema
from app.domain.receipt.rules.repository import ReceiptRulesRepository
from app.domain.receipt.rules.schema import (
    ReceiptRulesSchema,
    ReceiptRulesCreateSchema,
    ReceiptRulesUpdateSchema,
    ReceiptRulesSeedSchema,
    ReceiptRulesSeedEntrySchema,
)
from app.models import (
    User,
    ReceiptInterpretationProfile,
    ReceiptFieldRule,
    ReceiptIdentificationRule,
)
from app.shared.schemas import Message

logger = logging.getLogger(__name__)


class ReceiptRulesService:
    def __init__(self, repository: ReceiptRulesRepository) -> None:
        self.alias = "ReceiptInterpretationProfile"
        self.repository = repository
        self.logger_params = LoggingParams(
            logger=logger, service="ReceiptRulesService", operation="rules"
        )
        self.cache_service = CacheService(
            alias=self.alias,
            prefix="rules",
            logger_params=self.logger_params,
            schema_class=AccountSchema,
        )

    @classmethod
    def from_session(cls, session: AsyncSession) -> ReceiptRulesService:
        return cls(ReceiptRulesRepository(session))

    @staticmethod
    def _translate_error(exception: Exception) -> Exception:
        if isinstance(exception, ProfileReconciliationError):
            return HTTPException(HTTPStatus.UNPROCESSABLE_CONTENT, str(exception))
        if not isinstance(exception, IntegrityError):
            return exception
        pending = [exception.orig]
        seen: set[int] = set()
        while pending:
            error = pending.pop()
            if error is None or id(error) in seen:
                continue
            seen.add(id(error))
            constraint = getattr(getattr(error, "diag", None), "constraint_name", None)
            constraint = constraint or getattr(error, "constraint_name", None)
            if constraint == "uq_receipt_profiles_owner_institution_live":
                return HTTPException(
                    HTTPStatus.CONFLICT, "Institution profile already exists"
                )
            pending.extend(
                [getattr(error, "__cause__", None), getattr(error, "__context__", None)]
            )
        return exception

    @staticmethod
    def _check_entity(
        entity: ReceiptInterpretationProfile | None, *, writable: bool = False
    ) -> ReceiptInterpretationProfile:
        if entity is None:
            raise HTTPException(
                HTTPStatus.NOT_FOUND, "Receipt interpretation profile not found"
            )
        if writable and entity.user_id is None:
            raise HTTPException(HTTPStatus.FORBIDDEN, "System profile is read-only")
        return entity

    @asynccontextmanager
    async def _operation(
        self, operation: str, user_request: str, target_id: UUID | None = None
    ) -> AsyncIterator[None]:
        try:
            yield
        except Exception as exception:
            handle_service_exception(
                self._translate_error(exception),
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
                message=(
                    f"Receipt interpretation profile {operation} "
                    f"successfully: {target_id}"
                ),
                user_request=user_request,
            )

    async def create(
        self, user: User, payload: ReceiptRulesCreateSchema
    ) -> ReceiptRulesSchema:
        user_id, username = user.id, user.username
        entity = self._build_aggregate(user_id, payload)
        async with self._operation("create", username, entity.id):
            async with self.repository.transaction():
                rules = await self.repository.find_by_code(
                    user_id=user_id, institution_code=payload.institution_code
                )
                if rules is not None:
                    raise HTTPException(
                        HTTPStatus.CONFLICT, "Institution profile already exists"
                    )
                await self.repository.save(entity)
                result = ReceiptRulesSchema.model_validate(entity)
            return result

    @staticmethod
    def _build_aggregate(
        user_id: UUID | None,
        payload: ReceiptRulesCreateSchema | ReceiptRulesSeedEntrySchema,
    ) -> ReceiptInterpretationProfile:
        entity = ReceiptInterpretationProfile(
            user_id=user_id,
            name=payload.name,
            institution_code=payload.institution_code,
            is_active=payload.is_active,
        )
        entity.field_rules.extend(
            ReceiptFieldRule(profile_id=entity.id, **child.model_dump(mode="json"))
            for child in payload.field_rules
        )
        entity.identification_rules.extend(
            ReceiptIdentificationRule(
                profile_id=entity.id, **child.model_dump(mode="json")
            )
            for child in payload.identification_rules
        )
        return entity

    async def list_all(
        self, page_filter, user: User
    ) -> list[ReceiptRulesSchema] | CustomLimitOffsetPage[ReceiptRulesSchema]:
        user_id, username = user.id, user.username
        async with self._operation("list_all", username, user_id):
            entities = await self.repository.list_all(page_filter, user_id=user_id)
            if isinstance(entities, CustomLimitOffsetPage):
                return CustomLimitOffsetPage[ReceiptRulesSchema](
                    **entities.model_dump(exclude={"items"}),
                    items=[
                        ReceiptRulesSchema.model_validate(entity)
                        for entity in entities.items
                    ],
                )
            return [ReceiptRulesSchema.model_validate(entity) for entity in entities]

    async def find_by(self, profile_id: UUID, user: User) -> ReceiptRulesSchema:
        user_id, username = user.id, user.username
        async with self._operation("find_by", username, profile_id):
            entity = self._check_entity(
                await self.repository.find_by(id=profile_id, user_id=user_id)
            )
            return ReceiptRulesSchema.model_validate(entity)

    async def extract_source_institution(
        self, profile_id: UUID, text: str, user: User, *, identified: bool
    ) -> SourceExtractionResult:
        user_id, username = user.id, user.username
        async with self._operation("extract_source_institution", username, profile_id):
            entity = self._check_entity(
                await self.repository.find_by(id=profile_id, user_id=user_id)
            )
            if not entity.is_active:
                return SourceExtractionResult(status="not_found")
            rule = next(
                (
                    child
                    for child in entity.field_rules
                    if child.field_name == "source_institution"
                    and child.is_active
                    and child.deleted_at is None
                ),
                None,
            )
            if rule is None:
                return SourceExtractionResult(status="not_found")
            payload = ReceiptFieldRuleCreateSchema.model_validate(
                {
                    "field_name": rule.field_name,
                    "configuration": rule.configuration,
                    "is_active": rule.is_active,
                }
            )
            return await extract_source(payload, text, identified=identified)

    async def update(
        self,
        profile_id: UUID,
        payload: ReceiptRulesUpdateSchema,
        user: User,
    ) -> Message:
        user_id, username = user.id, user.username
        async with self._operation("update", username, profile_id):
            async with self.repository.transaction():
                entity = self._check_entity(
                    await self.repository.find_by(
                        id=profile_id, user_id=user_id, for_update=True
                    ),
                    writable=True,
                )
                fields = (
                    build_reconciliation_plan(
                        payload.field_rules,
                        [c.id for c in entity.field_rules if c.deleted_at is None],
                    )
                    if payload.field_rules is not None
                    else None
                )
                identification = (
                    build_reconciliation_plan(
                        payload.identification_rules,
                        [
                            c.id
                            for c in entity.identification_rules
                            if c.deleted_at is None
                        ],
                    )
                    if payload.identification_rules is not None
                    else None
                )
                for key, value in payload.model_dump(
                    exclude_unset=True,
                    exclude={"field_rules", "identification_rules"},
                ).items():
                    setattr(entity, key, value)
                await self.repository.save(
                    entity, fields=fields, identification=identification
                )
            return Message(message=f"Update receipt profile {profile_id} successfully")

    async def delete(self, profile_id: UUID, user: User) -> Message:
        user_id, username = user.id, user.username
        async with self._operation("delete", username, profile_id):
            async with self.repository.transaction():
                entity = self._check_entity(
                    await self.repository.find_by(
                        id=profile_id, user_id=user_id, for_update=True
                    ),
                    writable=True,
                )
                await self.repository.delete(entity)
            return Message(message=f"Delete receipt profile {profile_id} successfully")

    async def seed_defaults(self, user: User) -> ReceiptRulesSeedSchema:
        user_id, username = user.id, user.username
        async with self._operation("seed_defaults", username):
            payloads = load_default_receipt_rules()
            created = 0
            skipped = 0
            async with self.repository.transaction():
                await self.repository.lock_seed()
                for payload in payloads:
                    owner_id = user_id if payload.institution_code is not None else None
                    existing = await self.repository.find_by_code(
                        institution_code=payload.institution_code, user_id=owner_id
                    )
                    if existing is not None:
                        skipped += 1
                        continue
                    await self.repository.save(self._build_aggregate(owner_id, payload))
                    created += 1
                result = ReceiptRulesSeedSchema(created=created, skipped=skipped)
            return result
