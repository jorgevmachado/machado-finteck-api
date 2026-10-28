from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from uuid import UUID

from sqlalchemy import ColumnElement, Select, Uuid, func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, Mapped, RelationshipProperty
from sqlalchemy.orm.interfaces import ORMOption

from app.core.pagination import CustomLimitOffsetPage, is_paginate
from app.core.pagination.pagination import get_limit_offset_params
from app.shared.schemas import FilterPage

logger = logging.getLogger(__name__)
_TRANSACTION_KEY = "app.temp.transaction_active"


class OwnedEntity(Protocol):
    id: Mapped[UUID]
    user_id: Mapped[UUID]


@dataclass(frozen=True)
class RelationFilter:
    relationship: str
    field: str


@dataclass(frozen=True)
class RangeFilter:
    field: str
    operator: Literal["gte", "lte"]


class BaseRepository[ModelT: OwnedEntity]:
    model: type[ModelT]
    filter_fields: tuple[str, ...] = ("id",)
    relation_filters: Mapping[str, RelationFilter] = {}
    range_filters: Mapping[str, RangeFilter] = {}
    order_fields: tuple[str, ...] = ("id",)
    default_order_by: str = "id"
    relations: tuple[ORMOption, ...] = ()

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        if (
            self.session.info.get(_TRANSACTION_KEY)
            or self.session.in_nested_transaction()
        ):
            raise RuntimeError("Nested experimental transactions are not supported")
        self.session.info[_TRANSACTION_KEY] = True
        try:
            if not self.session.in_transaction():
                await self.session.begin()
            yield
            await self.session.commit()
        except BaseException:
            try:
                await self.session.rollback()
            except BaseException:
                logger.exception("Failed to roll back experimental transaction")
            raise
        finally:
            self.session.info.pop(_TRANSACTION_KEY, None)

    def _require_transaction(self) -> None:
        if not self.session.info.get(_TRANSACTION_KEY):
            raise RuntimeError("Mutations must run inside transaction()")

    def _check_entity(self, entity: ModelT, user_id: UUID) -> None:
        self.require_owner(user_id)
        self._require_transaction()
        if not isinstance(entity, self.model) or entity.user_id != user_id:
            raise ValueError("Entity does not belong to the trusted owner")

    async def _check_stored_owner(self, entity: ModelT, user_id: UUID) -> None:
        with self.session.no_autoflush:
            owner = await self.session.scalar(
                select(self._column("user_id")).where(self._column("id") == entity.id)
            )
        if owner != user_id:
            raise ValueError("Stored entity does not belong to the trusted owner")

    async def save(self, entity: ModelT, *, user_id: UUID) -> ModelT:
        self._check_entity(entity, user_id)
        state = inspect(entity)
        if state.persistent or state.detached:
            await self._check_stored_owner(entity, user_id)
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def update(self, entity: ModelT, *, user_id: UUID) -> ModelT:
        self._check_entity(entity, user_id)
        await self._check_stored_owner(entity, user_id)
        merged = await self.session.merge(entity)
        await self.session.flush()
        await self.session.refresh(merged)
        return merged

    async def delete(self, entity: ModelT, *, user_id: UUID) -> None:
        self._check_entity(entity, user_id)
        await self._check_stored_owner(entity, user_id)
        await self._delete(entity)
        await self.session.flush()

    async def _delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)

    @staticmethod
    def require_owner(user_id: UUID) -> None:
        if not isinstance(user_id, UUID):
            raise ValueError("A trusted owner UUID is required")

    @staticmethod
    def _mapped_column(model: type, field: str) -> InstrumentedAttribute[Any]:
        attribute = getattr(model, field, None)
        if not isinstance(attribute, InstrumentedAttribute) or not hasattr(
            attribute.property, "columns"
        ):
            raise ValueError(f"Not a mapped column: {field}")
        return attribute

    def _column(self, field: str) -> InstrumentedAttribute[Any]:
        return self._mapped_column(self.model, field)

    def _relation(self, definition: RelationFilter) -> InstrumentedAttribute[Any]:
        relation = getattr(self.model, definition.relationship, None)
        if not isinstance(relation, InstrumentedAttribute) or not isinstance(
            relation.property, RelationshipProperty
        ):
            raise ValueError(f"Not a mapped relationship: {definition.relationship}")
        self._mapped_column(relation.property.mapper.class_, definition.field)
        return relation

    @staticmethod
    def _normalize_filter_value(
        column: InstrumentedAttribute[Any], value: object
    ) -> object:
        column_type = column.property.columns[0].type
        if (
            isinstance(column_type, Uuid)
            and column_type.as_uuid
            and isinstance(value, str)
        ):
            return UUID(value)
        return value

    def validate_filters(
        self, *, user_id: UUID, filters: Mapping[str, object]
    ) -> dict[str, object]:
        self.require_owner(user_id)
        criteria = {}
        for field, value in filters.items():
            if field == "user_id":
                raise ValueError(f"Unsupported filter: {field}")
            if field in self.relation_filters:
                definition = self.relation_filters[field]
                relation = self._relation(definition)
                column = self._mapped_column(
                    relation.property.mapper.class_, definition.field
                )
            elif field in self.range_filters:
                definition = self.range_filters[field]
                if definition.operator not in ("gte", "lte"):
                    raise ValueError(
                        f"Unsupported range operator: {definition.operator}"
                    )
                column = self._column(definition.field)
            elif field in self.filter_fields:
                column = self._column(field)
            else:
                raise ValueError(f"Unsupported filter: {field}")
            criteria[field] = self._normalize_filter_value(column, value)
        return criteria

    def prepare_lookup(
        self, *, user_id: UUID, filters: Mapping[str, object]
    ) -> dict[str, object]:
        criteria = self.validate_filters(user_id=user_id, filters=filters)
        if not criteria:
            raise ValueError("Lookup requires at least one resource criterion")
        return criteria

    def prepare_list(
        self, *, user_id: UUID, page_filter: FilterPage | None
    ) -> tuple[dict[str, object], str]:
        raw = page_filter.model_dump(exclude_none=True) if page_filter else {}
        order_by = raw.pop("order_by", self.default_order_by)
        self._order_direction(raw.pop("order", "asc"))
        for field in ("page", "offset", "limit", "clean_cache"):
            raw.pop(field, None)
        criteria = self.validate_filters(user_id=user_id, filters=raw)
        if order_by not in self.order_fields:
            raise ValueError(f"Unsupported ordering: {order_by}")
        self._column(order_by)
        return criteria, order_by

    @staticmethod
    def _order_direction(order: object) -> Literal["asc", "desc"]:
        if order not in ("asc", "desc"):
            raise ValueError(f"Unsupported order direction: {order}")
        return "desc" if order == "desc" else "asc"

    def _visibility(self) -> tuple[ColumnElement[bool], ...]:
        return ()

    def _build_query(self, *, user_id: UUID) -> Select[tuple[ModelT]]:
        self.require_owner(user_id)
        return select(self.model).where(
            self._column("user_id") == user_id,
            *self._visibility(),
        )

    def _build_filter(
        self, query: Select[tuple[ModelT]], filters: Mapping[str, object]
    ) -> Select[tuple[ModelT]]:
        for field, value in filters.items():
            if field in self.relation_filters:
                query = query.where(self._relation_predicate(field, value))
            elif field in self.range_filters:
                definition = self.range_filters[field]
                column = self._column(definition.field)
                predicate = (
                    column >= value if definition.operator == "gte" else column <= value
                )
                query = query.where(predicate)
            else:
                query = query.where(self._column(field) == value)
        return query

    def _relation_predicate(self, field: str, value: object) -> ColumnElement[bool]:
        definition = self.relation_filters[field]
        relation = self._relation(definition)
        column = self._mapped_column(relation.property.mapper.class_, definition.field)
        predicate = column == value
        return (
            relation.any(predicate)
            if relation.property.uselist
            else relation.has(predicate)
        )

    def _load_relations(self, query: Select[tuple[ModelT]]) -> Select[tuple[ModelT]]:
        return query.options(*self.relations)

    def _order_by(
        self, query: Select[tuple[ModelT]], *, order_by: str, order: str
    ) -> Select[tuple[ModelT]]:
        fields = [order_by] if order_by == "id" else [order_by, "id"]
        return query.order_by(
            *(
                self._column(field).desc()
                if order == "desc"
                else self._column(field).asc()
                for field in fields
            )
        )

    async def _execute_list(self, query: Select[tuple[ModelT]]) -> list[ModelT]:
        return list((await self.session.scalars(query)).unique().all())

    async def _list_paginate(
        self,
        query: Select[tuple[ModelT]],
        *,
        page_filter: FilterPage,
    ) -> CustomLimitOffsetPage[ModelT]:
        params = get_limit_offset_params(page_filter)
        total = await self.session.scalar(
            select(func.count()).select_from(query.order_by(None).subquery())
        )
        items = await self._execute_list(
            query.limit(params.limit).offset(params.offset)
        )
        return CustomLimitOffsetPage.create(items, params=params, total=total)

    async def list_all(
        self, *, user_id: UUID, page_filter: FilterPage | None = None
    ) -> list[ModelT] | CustomLimitOffsetPage[ModelT]:
        filters, order_by = self.prepare_list(user_id=user_id, page_filter=page_filter)
        query = self._build_query(user_id=user_id)
        query = self._build_filter(query, filters)
        query = self._load_relations(query)
        raw = page_filter.model_dump(exclude_none=True) if page_filter else {}
        query = self._order_by(
            query,
            order_by=order_by,
            order=self._order_direction(raw.get("order", "asc")),
        )
        if page_filter is not None and is_paginate(page_filter):
            return await self._list_paginate(query, page_filter=page_filter)
        return await self._execute_list(query)

    async def find_by(
        self, *, user_id: UUID, filters: Mapping[str, object]
    ) -> ModelT | None:
        criteria = self.prepare_lookup(user_id=user_id, filters=filters)
        query = self._build_query(user_id=user_id)
        query = self._build_filter(query, criteria)
        query = self._load_relations(query)
        return (await self.session.scalars(query)).unique().one_or_none()
