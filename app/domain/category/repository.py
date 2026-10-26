from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload, selectinload

from app.core.database import get_session
from app.core.pagination import CustomLimitOffsetPage, is_paginate
from app.core.pagination.pagination import get_limit_offset_params
from app.core.repository.base import BaseRepository
from app.domain.category.business import SubcategoryReconciliationPlan
from app.models import Category, Subcategory, utcnow
from app.shared.schemas import FilterPage

Session = Annotated[AsyncSession, Depends(get_session)]
_TRANSACTION_KEY = "app.domain.category.repository.transaction_active"
logger = logging.getLogger(__name__)


class CategoryRepository(BaseRepository[Category]):
    model = Category
    default_order_by = "created_at"

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        session_info = self.session.info
        if session_info.get(_TRANSACTION_KEY):
            raise RuntimeError(
                "Nested category repository transactions are not supported"
            )
        if self.session.in_nested_transaction():
            raise RuntimeError(
                "Nested category repository transactions are not supported"
            )

        session_info[_TRANSACTION_KEY] = True
        try:
            if not self.session.in_transaction():
                await self.session.begin()
            yield
            await self.session.commit()
        except BaseException:
            try:
                await self.session.rollback()
            except BaseException:
                logger.exception("Failed to roll back category aggregate transaction")
            raise
        finally:
            session_info.pop(_TRANSACTION_KEY, None)

    async def find_by(
        self,
        *,
        id: UUID,
        user_id: UUID,
        for_update: bool = False,
    ) -> Category | None:
        filters = (
            Category.id == id,
            Category.user_id == user_id,
            Category.deleted_at.is_(None),
        )
        child_loader = selectinload(
            Category.subcategories.and_(Subcategory.deleted_at.is_(None))
        )

        if not for_update:
            return await self.session.scalar(
                select(Category).where(*filters).options(child_loader)
            )

        locked_root = await self.session.scalar(
            select(Category)
            .where(*filters)
            .options(lazyload(Category.subcategories))
            .with_for_update(of=Category)
        )
        if locked_root is None:
            return None

        return await self.session.scalar(
            select(Category)
            .where(*filters)
            .options(child_loader)
            .execution_options(populate_existing=True)
        )

    async def find_subcategory_by_id(
        self, *, subcategory_id: UUID, user_id: UUID
    ) -> Subcategory | None:
        return await self.session.scalar(
            select(Subcategory)
            .join(Subcategory.category)
            .where(
                Subcategory.id == subcategory_id,
                Subcategory.deleted_at.is_(None),
                Category.user_id == user_id,
                Category.deleted_at.is_(None),
            )
        )

    async def find_by_name(
        self,
        *,
        name: str,
        user_id: UUID,
        exclude_id: UUID | None = None,
    ) -> Category | None:
        query = select(Category).where(
            Category.name == name,
            Category.user_id == user_id,
            Category.deleted_at.is_(None),
        )
        if exclude_id is not None:
            query = query.where(Category.id != exclude_id)
        return await self.session.scalar(query)

    async def list_all(
        self, page_filter: Annotated[FilterPage, Query()] = None
    ) -> list[Category] | CustomLimitOffsetPage[Category]:
        if page_filter is None or getattr(page_filter, "user_id", None) is None:
            raise ValueError("Category listings require an owner user_id filter")

        conditions: list[Any] = [
            Category.user_id == page_filter.user_id,
            Category.deleted_at.is_(None),
        ]
        name = getattr(page_filter, "name", None)
        if name is not None:
            conditions.append(Category.name == name)

        query = (
            select(Category)
            .where(*conditions)
            .options(
                selectinload(
                    Category.subcategories.and_(Subcategory.deleted_at.is_(None))
                )
            )
            .order_by(Category.created_at, Category.id)
        )
        if not is_paginate(page_filter):
            result = await self.session.scalars(query)
            return result.all()

        params = get_limit_offset_params(page_filter)
        total = int(
            await self.session.scalar(
                select(func.count(Category.id)).where(*conditions)
            )
            or 0
        )
        result = await self.session.scalars(
            query.limit(params.limit).offset(params.offset)
        )
        return CustomLimitOffsetPage.create(
            items=result.all(),
            total=total,
            params=params,
        )

    async def save(
        self,
        entity: Category,
        reconciliation: SubcategoryReconciliationPlan | None = None,
    ) -> Category:
        self._require_transaction()
        now = utcnow()
        if reconciliation is not None:
            live_children = {
                child.id: child
                for child in entity.subcategories
                if child.deleted_at is None
            }
            for update in reconciliation.updates:
                child = live_children[update.id]
                child.name = update.name
                child.icon = update.icon
                child.color = update.color
                child.is_active = update.is_active
                child.order = update.order
                child.updated_at = now

            for child_id in reconciliation.remove_ids:
                child = live_children[child_id]
                child.deleted_at = now
                child.is_active = False
                child.updated_at = now

            for create in reconciliation.creates:
                entity.subcategories.append(
                    Subcategory(
                        name=create.name,
                        icon=create.icon,
                        color=create.color,
                        is_active=create.is_active,
                        order=create.order,
                    )
                )

        state = self._state(entity)
        if state.persistent:
            entity.updated_at = now
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, entity: Category) -> Category:
        return await self.save(entity)

    async def delete(self, entity: Category) -> None:
        self._require_transaction()
        now = utcnow()
        entity.deleted_at = now
        entity.is_active = False
        entity.updated_at = now
        for child in entity.subcategories:
            if child.deleted_at is not None:
                continue
            child.deleted_at = now
            child.is_active = False
            child.updated_at = now
        await self.session.flush()

    def _require_transaction(self) -> None:
        if not self.session.info.get(_TRANSACTION_KEY):
            raise RuntimeError(
                "CategoryRepository save/delete must run inside transaction()"
            )

    @staticmethod
    def _state(entity: Category):
        from sqlalchemy import inspect

        return inspect(entity)
