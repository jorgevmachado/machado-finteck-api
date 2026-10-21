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
from app.core.pagination import CustomLimitOffsetPage
from app.domain.receipt.receipt_interpretation_profile.business import (
    ProfileReconciliationError,
    build_reconciliation_plan,
)
from app.domain.receipt.receipt_interpretation_profile.repository import (
    ReceiptInterpretationProfileRepository,
)
from app.domain.receipt.receipt_interpretation_profile.schema import (
    ReceiptInterpretationProfileCreateSchema,
    ReceiptInterpretationProfileFilter,
    ReceiptInterpretationProfileSchema,
    ReceiptInterpretationProfileUpdateSchema,
)
from app.models import (
    ReceiptFieldRule,
    ReceiptIdentificationRule,
    ReceiptInterpretationProfile,
    User,
)
from app.shared.schemas import Message

logger = logging.getLogger(__name__)


class ReceiptInterpretationProfileService:
    def __init__(self, repository: ReceiptInterpretationProfileRepository) -> None:
        self.repository = repository
        self.logger_params = LoggingParams(
            logger=logger,
            service="ReceiptInterpretationProfileService",
            operation="receipt_interpretation_profile",
        )

    @classmethod
    def from_session(cls, session: AsyncSession) -> ReceiptInterpretationProfileService:
        return cls(ReceiptInterpretationProfileRepository(session))

    @asynccontextmanager
    async def _operation(
        self, operation: str, user_request: str, target_id: UUID
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
        self, user: User, payload: ReceiptInterpretationProfileCreateSchema
    ) -> ReceiptInterpretationProfileSchema:
        user_id, username = user.id, user.username
        entity = ReceiptInterpretationProfile(
            user_id=user_id,
            name=payload.name,
            institution_code=payload.institution_code,
            is_active=payload.is_active,
        )
        async with self._operation("create", username, entity.id):
            async with self.repository.transaction():
                if (
                    await self.repository.find_by_code(
                        user_id=user_id, institution_code=payload.institution_code
                    )
                    is not None
                ):
                    raise HTTPException(409, "Institution profile already exists")
                entity.field_rules.extend(
                    ReceiptFieldRule(
                        profile_id=entity.id, **child.model_dump(mode="json")
                    )
                    for child in payload.field_rules
                )
                entity.identification_rules.extend(
                    ReceiptIdentificationRule(
                        profile_id=entity.id, **child.model_dump(mode="json")
                    )
                    for child in payload.identification_rules
                )
                await self.repository.save(entity)
                result = ReceiptInterpretationProfileSchema.model_validate(entity)
            return result

    async def list_all(
        self, page_filter: ReceiptInterpretationProfileFilter, user: User
    ) -> (
        list[ReceiptInterpretationProfileSchema]
        | CustomLimitOffsetPage[ReceiptInterpretationProfileSchema]
    ):
        user_id, username = user.id, user.username
        async with self._operation("list_all", username, user_id):
            entities = await self.repository.list_all(page_filter, user_id=user_id)
            if isinstance(entities, CustomLimitOffsetPage):
                return CustomLimitOffsetPage[ReceiptInterpretationProfileSchema](
                    **entities.model_dump(exclude={"items"}),
                    items=[
                        ReceiptInterpretationProfileSchema.model_validate(entity)
                        for entity in entities.items
                    ],
                )
            return [
                ReceiptInterpretationProfileSchema.model_validate(entity)
                for entity in entities
            ]

    async def find_by(
        self, profile_id: UUID, user: User
    ) -> ReceiptInterpretationProfileSchema:
        user_id, username = user.id, user.username
        async with self._operation("find_by", username, profile_id):
            entity = self._check_entity(
                await self.repository.find_by(id=profile_id, user_id=user_id)
            )
            return ReceiptInterpretationProfileSchema.model_validate(entity)

    async def update(
        self,
        profile_id: UUID,
        payload: ReceiptInterpretationProfileUpdateSchema,
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

    @staticmethod
    def _check_entity(
        entity: ReceiptInterpretationProfile | None, *, writable: bool = False
    ) -> ReceiptInterpretationProfile:
        if entity is None:
            raise HTTPException(404, "Receipt interpretation profile not found")
        if writable and entity.user_id is None:
            raise HTTPException(403, "System profile is read-only")
        return entity

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
                return HTTPException(409, "Institution profile already exists")
            pending.extend(
                [getattr(error, "__cause__", None), getattr(error, "__context__", None)]
            )
        return exception
