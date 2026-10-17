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
from app.domain.account.repository import AccountRepository
from app.domain.account.schema import (
    AccountSchema,
    AccountCreateSchema,
    AccountUpdateSchema,
)
from app.models import Account, User
from app.shared.schemas import FilterPage, Message

logger = logging.getLogger(__name__)


class AccountService:
    def __init__(self, repository: AccountRepository) -> None:
        self.alias = "Account"
        self.repository = repository
        self.logger_params = LoggingParams(
            logger=logger, service="AccountService", operation="account"
        )
        self.cache_service = CacheService(
            alias=self.alias,
            prefix="account",
            logger_params=self.logger_params,
            schema_class=AccountSchema,
        )

    @classmethod
    def from_session(cls, session: AsyncSession) -> AccountService:
        return cls(AccountRepository(session))

    async def list_all(
        self, page_filter: FilterPage, user: User
    ) -> list[Account] | CustomLimitOffsetPage[Account]:
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
        name: str | None = None,
        user_request: str | None = None,
        without_throw: bool = False,
    ) -> Account | None:
        try:
            result = await self.repository.find_by(id=id, name=name, user_id=user_id)
            if result is None and not without_throw:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND, detail="Account not found"
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

    async def create(
        self,
        user: User,
        payload: AccountCreateSchema,
    ) -> Account:
        try:
            entity = await self.find_by(
                user_id=user.id, name=payload.name, without_throw=True
            )
            if entity:
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT, detail="Account already exists"
                )

            result = await self.repository.save(
                entity=Account(
                    user_id=user.id,
                    icon=payload.icon,
                    type=payload.type,
                    name=payload.name,
                    color=payload.color,
                    agency=payload.agency,
                    is_active=payload.is_active,
                    description=payload.description,
                    account_number=payload.account_number,
                    financial_institution=payload.financial_institution,
                )
            )
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
        param: str,
        update_schema: AccountUpdateSchema,
        user: User,
    ) -> Message:
        try:
            entity = await self.find_by(
                id=param, user_id=user.id, user_request=user.username
            )
            if entity is None:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND, detail="Account not found"
                )

            for key, value in update_schema.model_dump(exclude_unset=True).items():
                setattr(entity, key, value)

            await self._invalidate_cache(identifier=param)
            await self.repository.update(entity=entity)
            log_service_success(
                self.logger_params,
                operation="update",
                message=f"Update {self.alias} {param} successfully",
                user_request=user.username,
            )
            return Message(message=f"Update {self.alias} {param} successfully")
        except Exception as exception:
            handle_service_exception(
                exception,
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="update",
                user_request=user.username,
                raise_exception=True,
            )

    async def delete(self, user: User, account_id: str) -> Message:
        try:
            entity = await self.find_by(
                id=account_id, user_id=user.id, without_throw=True
            )
            if not entity:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND, detail="Account not found"
                )

            await self.repository.delete(entity=entity)
            log_service_success(
                self.logger_params,
                operation="delete",
                message=f"Delete {self.alias} {account_id} successfully",
                user_request=user.username,
            )
            return Message(message=f"Delete {self.alias} {account_id} successfully")
        except Exception as exception:
            handle_service_exception(
                exception,
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="delete",
                user_request=user.username,
                raise_exception=True,
            )
