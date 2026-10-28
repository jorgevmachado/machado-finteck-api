from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import lazyload, selectinload

from app.core.pagination import CustomLimitOffsetPage, is_paginate
from app.core.pagination.pagination import get_limit_offset_params
from app.domain.category.business import SubcategoryReconciliationPlan
from app.models import Category, Subcategory, utcnow
from app.shared.schemas import FilterPage
from app.temp import BaseRepository

logger = logging.getLogger(__name__)

_ACTIVE_SUBCATEGORIES = selectinload(
    Category.subcategories.and_(Subcategory.deleted_at.is_(None))
).lazyload(Subcategory.payments)


class CategoryRepository(BaseRepository[Category]):
    model = Category
    default_order_by = "created_at"
    order_fields = ("created_at", "name")
    filter_fields = ("id", "name")
    relations = (_ACTIVE_SUBCATEGORIES,)

    async def find_by(
        self,
        *,
        user_id: UUID,
        filters: Mapping[str, object] | None = None,
        id: UUID | None = None,
        for_update: bool = False,
    ) -> Category | None:
        if id is not None:
            filters = {"id": id}
        elif filters is None:
            raise ValueError("find_by requires id or filters")
        if set(filters) - {"id"}:
            raise ValueError("Category lookups support only the id criterion")
        raw_id = filters["id"]
        identifier = raw_id if isinstance(raw_id, UUID) else UUID(str(raw_id))
        conditions = (
            Category.id == identifier,
            Category.user_id == user_id,
            Category.deleted_at.is_(None),
        )
        if not for_update:
            return await self.session.scalar(
                select(Category).where(*conditions).options(_ACTIVE_SUBCATEGORIES)
            )

        locked_root = await self.session.scalar(
            select(Category)
            .where(*conditions)
            .options(lazyload(Category.subcategories))
            .with_for_update(of=Category)
        )
        if locked_root is None:
            return None

        return await self.session.scalar(
            select(Category)
            .where(*conditions)
            .options(_ACTIVE_SUBCATEGORIES)
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
        self, *, user_id: UUID | None, page_filter: FilterPage | None = None
    ) -> list[Category] | CustomLimitOffsetPage[Category]:
        if user_id is None:
            raise ValueError("A trusted owner UUID is required")
        self.require_owner(user_id)

        conditions: list[Any] = [
            Category.user_id == user_id,
            Category.deleted_at.is_(None),
        ]
        name = getattr(page_filter, "name", None)
        if name is not None:
            conditions.append(Category.name == name)

        query = (
            select(Category)
            .where(*conditions)
            .options(_ACTIVE_SUBCATEGORIES)
            .order_by(Category.created_at, Category.id)
        )
        if page_filter is not None and is_paginate(page_filter):
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
                items=list(result.all()),
                total=total,
                params=params,
            )

        result = await self.session.scalars(query)
        return list(result.all())

    async def save(
        self,
        entity: Category,
        *,
        user_id: UUID | None = None,
        reconciliation: SubcategoryReconciliationPlan | None = None,
    ) -> Category:
        if user_id is not None:
            self._check_entity(entity, user_id)
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
        if state is not None and state.persistent:
            entity.updated_at = now
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(
        self, entity: Category, *, user_id: UUID | None = None
    ) -> Category:
        return await self.save(entity, user_id=user_id)

    async def delete(self, entity: Category, *, user_id: UUID | None = None) -> None:
        if user_id is not None:
            self._check_entity(entity, user_id)
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

    def _visibility(self) -> tuple[Any, ...]:
        return (Category.deleted_at.is_(None),)

    @staticmethod
    def _state(entity: Category):
        from sqlalchemy import inspect

        return inspect(entity)
