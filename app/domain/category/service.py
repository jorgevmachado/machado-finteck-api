from __future__ import annotations

import logging
from http import HTTPStatus
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import handle_service_exception
from app.core.logging import LoggingParams, log_service_success
from app.core.pagination import CustomLimitOffsetPage
from app.domain.category.business import (
    CategoryReconciliationError,
    build_subcategory_reconciliation_plan,
)
from app.domain.category.defaults import load_default_categories
from app.domain.category.repository import CategoryRepository
from app.domain.category.schema import (
    CategoryCreateSchema,
    CategorySeedSchema,
    CategoryUpdateSchema,
)
from app.models import Category, Subcategory, User
from app.shared.schemas import FilterPage, Message

logger = logging.getLogger(__name__)


class CategoryService:
    def __init__(self, repository: CategoryRepository) -> None:
        self.alias = "Category"
        self.repository = repository
        self.logger_params = LoggingParams(
            logger=logger, service="CategoryService", operation="category"
        )

    @classmethod
    def from_session(cls, session: AsyncSession) -> CategoryService:
        return cls(CategoryRepository(session))

    async def list_all(
        self, page_filter: FilterPage, user: User
    ) -> list[Category] | CustomLimitOffsetPage[Category]:
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
        id: UUID,
        user_id: UUID,
        user_request: str | None = None,
    ) -> Category:
        try:
            result = await self.repository.find_by(id=id, user_id=user_id)
            if result is None:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND, detail="Category not found"
                )
            log_service_success(
                self.logger_params,
                operation="find_by",
                message="Find by Category successfully",
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

    async def create(self, user: User, payload: CategoryCreateSchema) -> Category:
        user_request = user.username
        try:
            async with self.repository.transaction():
                duplicate = await self.repository.find_by_name(
                    name=payload.name, user_id=user.id
                )
                if duplicate is not None:
                    raise HTTPException(
                        status_code=HTTPStatus.CONFLICT,
                        detail="Category already exists",
                    )
                entity = self._build_aggregate(user.id, payload)
                result = await self.repository.save(entity=entity)
            log_service_success(
                self.logger_params,
                operation="create",
                message=f"Create Category {payload.name} successfully",
                user_request=user_request,
            )
            return result
        except Exception as exception:
            handle_service_exception(
                self._translate_mutation_error(exception),
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="create",
                user_request=user_request,
                raise_exception=True,
            )

    async def seed_defaults(self, user: User) -> CategorySeedSchema:
        user_request = user.username
        try:
            payloads = load_default_categories()
            created = 0
            skipped = 0
            async with self.repository.transaction():
                for payload in payloads:
                    existing = await self.repository.find_by_name(
                        name=payload.name, user_id=user.id
                    )
                    if existing is not None:
                        skipped += 1
                        continue
                    await self.repository.save(
                        entity=self._build_aggregate(user.id, payload)
                    )
                    created += 1
            result = CategorySeedSchema(created=created, skipped=skipped)
            log_service_success(
                self.logger_params,
                operation="seed_defaults",
                message=f"Seed categories successfully: created={created}, skipped={skipped}",
                user_request=user_request,
            )
            return result
        except Exception as exception:
            handle_service_exception(
                self._translate_mutation_error(exception),
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="seed_defaults",
                user_request=user_request,
                raise_exception=True,
            )

    @staticmethod
    def _build_aggregate(user_id: UUID, payload: CategoryCreateSchema) -> Category:
        entity = Category(
            user_id=user_id,
            name=payload.name,
            icon=payload.icon,
            color=payload.color,
            is_active=payload.is_active,
        )
        entity.subcategories = [
            Subcategory(**child.model_dump())
            for child in sorted(payload.subcategories, key=lambda child: child.order)
        ]
        return entity

    async def update(
        self,
        category_id: UUID,
        payload: CategoryUpdateSchema,
        user: User,
    ) -> Message:
        user_request = user.username
        try:
            async with self.repository.transaction():
                entity = await self.repository.find_by(
                    id=category_id, user_id=user.id, for_update=True
                )
                if entity is None:
                    raise HTTPException(
                        status_code=HTTPStatus.NOT_FOUND, detail="Category not found"
                    )
                plan = None
                if payload.subcategories is not None:
                    plan = build_subcategory_reconciliation_plan(
                        payload.subcategories,
                        [
                            child.id
                            for child in entity.subcategories
                            if child.deleted_at is None
                        ],
                    )
                update_data = payload.model_dump(
                    exclude_unset=True, exclude={"subcategories"}
                )
                if "name" in update_data:
                    duplicate = await self.repository.find_by_name(
                        name=update_data["name"],
                        user_id=user.id,
                        exclude_id=entity.id,
                    )
                    if duplicate is not None:
                        raise HTTPException(
                            status_code=HTTPStatus.CONFLICT,
                            detail="Category already exists",
                        )
                for key, value in update_data.items():
                    setattr(entity, key, value)
                await self.repository.save(entity=entity, reconciliation=plan)
            message = f"Update Category {category_id} successfully"
            log_service_success(
                self.logger_params,
                operation="update",
                message=message,
                user_request=user_request,
            )
            return Message(message=message)
        except Exception as exception:
            handle_service_exception(
                self._translate_mutation_error(exception),
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="update",
                user_request=user_request,
                raise_exception=True,
            )

    async def delete(self, user: User, category_id: UUID) -> Message:
        user_request = user.username
        try:
            async with self.repository.transaction():
                entity = await self.repository.find_by(
                    id=category_id, user_id=user.id, for_update=True
                )
                if entity is None:
                    raise HTTPException(
                        status_code=HTTPStatus.NOT_FOUND, detail="Category not found"
                    )
                await self.repository.delete(entity=entity)
            message = f"Delete Category {category_id} successfully"
            log_service_success(
                self.logger_params,
                operation="delete",
                message=message,
                user_request=user_request,
            )
            return Message(message=message)
        except Exception as exception:
            handle_service_exception(
                self._translate_mutation_error(exception),
                logger=self.logger_params.logger,
                service=self.logger_params.service,
                operation="delete",
                user_request=user_request,
                raise_exception=True,
            )

    @staticmethod
    def _translate_mutation_error(exception: Exception) -> Exception:
        if isinstance(exception, CategoryReconciliationError):
            return HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_CONTENT,
                detail=str(exception),
            )
        if not isinstance(exception, IntegrityError):
            return exception

        # SQLAlchemy driver adapters may wrap the original driver diagnostic.
        pending = [exception.orig]
        seen: set[int] = set()
        while pending:
            error = pending.pop()
            if error is None or id(error) in seen:
                continue
            seen.add(id(error))
            diagnostic = getattr(error, "diag", None)
            constraint = getattr(diagnostic, "constraint_name", None) or getattr(
                error, "constraint_name", None
            )
            if constraint == "uq_categories_owner_name_live":
                return HTTPException(
                    status_code=HTTPStatus.CONFLICT,
                    detail="Category already exists",
                )
            if constraint == "uq_subcategories_category_live_order":
                return HTTPException(
                    status_code=HTTPStatus.UNPROCESSABLE_CONTENT,
                    detail="Subcategory orders must be unique",
                )
            pending.extend(
                [
                    getattr(error, "__cause__", None),
                    getattr(error, "__context__", None),
                ]
            )
        return exception
