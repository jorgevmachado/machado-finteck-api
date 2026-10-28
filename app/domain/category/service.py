from __future__ import annotations

import logging
from http import HTTPStatus
from typing import cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.core.logging import LoggingParams
from app.domain.category.business import (
    CategoryReconciliationError,
    build_subcategory_reconciliation_plan,
)
from app.domain.category.defaults import load_default_categories
from app.domain.category.repository import CategoryRepository
from app.domain.category.schema import (
    CategoryCreateSchema,
    CategorySchema,
    CategorySeedSchema,
    CategoryUpdateSchema,
)
from app.models import Category, Subcategory, User
from app.shared.schemas import Message
from app.temp.service import BaseService

logger = logging.getLogger(__name__)


class CategoryService(
    BaseService[
        Category,
        CategoryCreateSchema,
        CategoryUpdateSchema,
        CategorySchema,
    ]
):
    repository_class = CategoryRepository
    repository: CategoryRepository

    def __init__(self, repository: CategoryRepository) -> None:
        super().__init__(
            repository,
            alias="Category",
            logger_params=LoggingParams(
                logger=logger,
                service="CategoryService",
                operation="category",
            ),
        )

    def _build_entity(self, user_id: UUID, data: dict[str, object]) -> Category:
        payload = CategoryCreateSchema.model_validate(data)
        return self._build_aggregate(user_id, payload)

    async def _normalize(
        self,
        data: dict[str, object],
        user: User,
        entity_id: UUID | None = None,
    ) -> dict[str, object]:
        name = data.get("name")
        if name is None:
            return data
        duplicate = await self.repository.find_by_name(
            name=cast(str, name), user_id=user.id, exclude_id=entity_id
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT, detail="Category already exists"
            )
        return data

    async def seed_defaults(self, user: User) -> CategorySeedSchema:
        async with self._operation("seed_defaults", user.username):
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
            return CategorySeedSchema(created=created, skipped=skipped)

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
        identifier: UUID | str,
        payload: CategoryUpdateSchema,
        user: User,
    ) -> Message:
        async with self._operation("update", user.username, identifier):
            return await self._update(cast(UUID, identifier), payload, user)

    async def _update(
        self, identifier: UUID, payload: CategoryUpdateSchema, user: User
    ) -> Message:
        async with self.repository.transaction():
            entity = await self.repository.find_by(
                id=identifier, user_id=user.id, for_update=True
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
                    name=cast(str, update_data["name"]),
                    user_id=user.id,
                    exclude_id=entity.id,
                )
                if duplicate is not None:
                    raise HTTPException(
                        status_code=HTTPStatus.CONFLICT,
                        detail="Category already exists",
                    )
            for key, value in update_data.items():
                self.repository._column(key)
                setattr(entity, key, value)
            await self.repository.save(
                entity=entity, user_id=user.id, reconciliation=plan
            )
        return Message(message=f"Update {self.alias} {identifier} successfully")

    async def delete(self, user: User, identifier: UUID | str) -> Message:
        async with self._operation("delete", user.username, identifier):
            return await self._delete(user, cast(UUID, identifier))

    async def _delete(self, user: User, identifier: UUID) -> Message:
        async with self.repository.transaction():
            entity = await self.repository.find_by(
                id=identifier, user_id=user.id, for_update=True
            )
            if entity is None:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND, detail="Category not found"
                )
            await self.repository.delete(entity, user_id=user.id)
        return Message(message=f"Delete {self.alias} {identifier} successfully")

    async def find_subcategory_by_id(
        self,
        *,
        subcategory_id: UUID,
        user_id: UUID,
        user_request: str | None = None,
    ) -> Subcategory:
        async with self._operation("find_subcategory_by_id", user_request or ""):
            result = await self.repository.find_subcategory_by_id(
                subcategory_id=subcategory_id, user_id=user_id
            )
            if result is None:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND,
                    detail="Subcategory not found",
                )
            return result

    def _translate_exception(self, exception: Exception) -> Exception:
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
