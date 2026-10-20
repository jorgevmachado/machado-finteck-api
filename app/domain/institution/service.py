from __future__ import annotations

import logging
from http import HTTPStatus
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache.service import CacheService
from app.core.exceptions import handle_service_exception
from app.core.logging import LoggingParams, log_service_success
from app.core.pagination import CustomLimitOffsetPage
from app.domain.institution.repository import InstitutionRepository
from app.domain.institution.schema import InstitutionCreateSchema, InstitutionSchema, InstitutionUpdateSchema
from app.models import Institution, User
from app.shared.schemas import FilterPage, Message
from app.shared.utils.string import to_snake_case

logger = logging.getLogger(__name__)


class InstitutionService:
    def __init__(self, repository: InstitutionRepository) -> None:
        self.alias = "Institution"
        self.repository = repository
        self.logger_params = LoggingParams(
            logger=logger, service="InstitutionService", operation="institution"
        )
        self.cache_service = CacheService(
            alias=self.alias,
            prefix="institution",
            logger_params=self.logger_params,
            schema_class=InstitutionSchema,
        )

    @classmethod
    def from_session(cls, session: AsyncSession) -> InstitutionService:
        return cls(InstitutionRepository(session))

    async def list_all(
        self, page_filter: FilterPage, user: User
    ) -> list[Institution] | CustomLimitOffsetPage[Institution]:
        try:
            result = await self.repository.list_all(
                page_filter=page_filter.with_updates(user_id=user.id)
            )
            log_service_success(
                self.logger_params,
                operation="list_all",
                message="List all successfully",
                user_request=user.username,
            )
            return result
        except Exception as exception:
            handle_service_exception(
                exception,
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="list_all",
                user_request=user.username,
                raise_exception=True,
            )

    async def find_by(
        self,
        *,
        user_id: UUID,
        id: str | UUID | None = None,
        name_code: str | None = None,
        user_request: str | None = None,
        without_throw: bool = False,
    ) -> Institution | None:
        try:
            result = await self.repository.find_by(
                id=id, name_code=name_code, user_id=user_id
            )
            if result is None and not without_throw:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND, detail="Institution not found"
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

    async def _invalidate_cache(self, identifier: str | None = None) -> None:
        try:
            await self.cache_service.delete_with_parent_cache()
            if identifier:
                key = self.cache_service.build_key_one(param=identifier)
                await self.cache_service.cache.delete_cache(key)
        except Exception:
            self.logger_params.logger.warning(
                "Cache invalidation skipped for %s due to an infrastructure error.",
                self.alias,
                exc_info=True,
            )

    async def create(self, user: User, payload: InstitutionCreateSchema) -> Institution:
        try:
            name_code = to_snake_case(payload.name)
            entity = await self.find_by(
                user_id=user.id, name_code=name_code, without_throw=True
            )
            if entity:
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT, detail="Institution already exists"
                )

            result = await self.repository.save(
                entity=Institution(
                    user_id=user.id,
                    name=payload.name,
                    name_code=name_code,
                )
            )
            await self._invalidate_cache()
            log_service_success(
                self.logger_params,
                operation="create",
                message=f"Create {self.alias} {payload.name} successfully",
                user_request=user.username,
            )
            return result
        except Exception as exception:
            handle_service_exception(
                exception,
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="create",
                user_request=user.username,
                raise_exception=True,
            )

    async def update(
        self,
        institution_id: str,
        payload: InstitutionUpdateSchema,
        user: User,
    ) -> Message:
        try:
            entity = await self.find_by(
                id=institution_id, user_id=user.id, user_request=user.username
            )
            if entity is None:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND, detail="Institution not found"
                )

            update_data = payload.model_dump(exclude_unset=True)
            if "name" in update_data:
                name_code = to_snake_case(update_data["name"])
                duplicate = await self.find_by(
                    user_id=user.id,
                    name_code=name_code,
                    without_throw=True,
                )
                if duplicate is not None and duplicate.id != entity.id:
                    raise HTTPException(
                        status_code=HTTPStatus.CONFLICT,
                        detail="Institution already exists",
                    )
                update_data["name_code"] = name_code

            for key, value in update_data.items():
                setattr(entity, key, value)

            await self.repository.update(entity=entity)
            await self._invalidate_cache(identifier=institution_id)
            log_service_success(
                self.logger_params,
                operation="update",
                message=f"Update {self.alias} {institution_id} successfully",
                user_request=user.username,
            )
            return Message(message=f"Update {self.alias} {institution_id} successfully")
        except Exception as exception:
            handle_service_exception(
                exception,
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="update",
                user_request=user.username,
                raise_exception=True,
            )

    async def delete(self, user: User, institution_id: str) -> Message:
        try:
            entity = await self.find_by(
                id=institution_id, user_id=user.id, without_throw=True
            )
            if entity is None:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND, detail="Institution not found"
                )

            await self.repository.delete(entity=entity)
            await self._invalidate_cache(identifier=institution_id)
            log_service_success(
                self.logger_params,
                operation="delete",
                message=f"Delete {self.alias} {institution_id} successfully",
                user_request=user.username,
            )
            return Message(message=f"Delete {self.alias} {institution_id} successfully")
        except Exception as exception:
            handle_service_exception(
                exception,
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="delete",
                user_request=user.username,
                raise_exception=True,
            )
