from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from hashlib import sha256
from http import HTTPStatus
import json
from logging import LoggerAdapter
import re
from typing import Any, Self, cast
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache.service import CacheService
from app.core.exceptions import handle_service_exception
from app.core.logging import LoggingParams, log_service_success
from app.core.pagination import CustomLimitOffsetPage
from app.models import User
from app.shared.schemas import FilterPage, Message
from app.temp.repository import BaseRepository, OwnedEntity

_MANAGED_FIELDS = frozenset({"id", "user_id", "created_at", "updated_at", "deleted_at"})
_CRITERIA = TypeAdapter(dict[str, object])


class BaseService[
    ModelT: OwnedEntity,
    CreateT: BaseModel = BaseModel,
    UpdateT: BaseModel = BaseModel,
    SchemaT: BaseModel = BaseModel,
](ABC):
    repository_class: type[BaseRepository[ModelT]] | None = None

    @classmethod
    def from_session(cls, session: AsyncSession, **kwargs: Any) -> Self:
        if cls.repository_class is None:
            raise TypeError(f"{cls.__name__} must declare repository_class")
        return cls(cls.repository_class(session), **kwargs)

    def __init__(
        self,
        repository: BaseRepository[ModelT],
        *,
        alias: str,
        logger_params: LoggingParams,
        schema_class: type[SchemaT] | None = None,
        cache_prefix: str | None = None,
        parents_alias: tuple[str, ...] = (),
        default_ttl: int = 86400,
    ) -> None:
        self.repository = repository
        self.alias = alias
        self.logger_params = logger_params
        self.schema_class = schema_class
        self.cache_prefix = cache_prefix or alias.replace(" ", "_").lower()
        self.parents_alias = parents_alias
        self.default_ttl = default_ttl
        if schema_class is not None:
            for resource in (self.cache_prefix, *parents_alias):
                if re.fullmatch(r"[a-z0-9_-]+", resource) is None:
                    raise ValueError(
                        "Cache namespaces must use lowercase letters, digits, _ or -"
                    )
            if default_ttl <= 0:
                raise ValueError("Cache TTL must be positive")

    def _translate_exception(self, exception: Exception) -> Exception:
        return exception

    @asynccontextmanager
    async def _operation(
        self, operation: str, user_request: str, target_id: UUID | str | None = None
    ) -> AsyncIterator[None]:
        logger = LoggerAdapter(
            self.logger_params.logger,
            {"target_id": str(target_id) if target_id else None},
            merge_extra=True,
        )
        try:
            yield
        except Exception as exception:
            handle_service_exception(
                self._translate_exception(exception),
                logger=logger,
                service=self.logger_params.service,
                operation=operation,
                user_request=user_request,
                raise_exception=True,
            )
        else:
            log_service_success(
                self.logger_params,
                logger=logger,
                operation=operation,
                message=f"{self.alias} {operation} successfully: {target_id}",
                user_request=user_request,
            )

    async def list_all(
        self, page_filter: FilterPage | None, user: User
    ) -> list[ModelT] | CustomLimitOffsetPage[ModelT]:
        async with self._operation("list_all", user.username):
            return await self.repository.list_all(
                user_id=user.id, page_filter=page_filter
            )

    def _schema(self) -> type[SchemaT]:
        if self.schema_class is None:
            raise RuntimeError("Cached reads require a configured response schema")
        return self.schema_class

    @staticmethod
    def _cache_scope(resource: str, user_id: UUID) -> str:
        return f"experimental:{resource}:{user_id}:"

    def _cache(self, user_id: UUID) -> CacheService:
        self.repository.require_owner(user_id)
        return CacheService(
            alias=self.alias,
            prefix=self._cache_scope(self.cache_prefix, user_id),
            logger_params=self.logger_params,
            schema_class=self._schema(),
            default_ttl=self.default_ttl,
        )

    @staticmethod
    def _criteria_key(criteria: Mapping[str, object]) -> str:
        normalized = _CRITERIA.dump_python(dict(criteria), mode="json")
        canonical = json.dumps(
            normalized, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        return sha256(canonical.encode("utf-8")).hexdigest()

    def _schema_list[ItemT](
        self, result: list[ItemT] | CustomLimitOffsetPage[ItemT]
    ) -> list[SchemaT] | CustomLimitOffsetPage[SchemaT]:
        schema = self._schema()
        if isinstance(result, list):
            return [
                schema.model_validate(item, from_attributes=True) for item in result
            ]
        return CustomLimitOffsetPage[schema](
            items=[
                schema.model_validate(item, from_attributes=True)
                for item in result.items
            ],
            meta=result.meta,
        )

    async def list_all_cached(
        self, page_filter: FilterPage | None, user: User
    ) -> list[SchemaT] | CustomLimitOffsetPage[SchemaT]:
        async with self._operation("list_all_cached", user.username):
            filters, order_by = self.repository.prepare_list(
                user_id=user.id, page_filter=page_filter
            )
            cache = self._cache(user.id)
            clean = page_filter.clean_cache if page_filter else False
            copied = (
                page_filter.model_copy(update={"clean_cache": None})
                if page_filter
                else None
            )
            criteria = copied.model_dump(exclude_none=True) if copied else {}
            criteria.update(filters, order_by=order_by)
            key = cache.build_key_list(
                FilterPage.build(query_digest=self._criteria_key(criteria))
            )
            if clean:
                await cache.delete_domain()
            cached = await cache.get_list(key)
            if cached is not None:
                if not isinstance(cached, (list, CustomLimitOffsetPage)):
                    raise ValueError("Unexpected cached pagination envelope")
                return self._schema_list(cached)
            result = self._schema_list(
                await self.repository.list_all(user_id=user.id, page_filter=copied)
            )
            await cache.set_list(key, result)
            return result

    async def find_one_cached(
        self, *, user: User, filters: Mapping[str, object], clean_cache: bool = False
    ) -> SchemaT:
        async with self._operation("find_one_cached", user.username):
            criteria = self.repository.prepare_lookup(user_id=user.id, filters=filters)
            cache = self._cache(user.id)
            key = cache.build_key_one(self._criteria_key(criteria))
            if clean_cache:
                await cache.delete_cache(cache_key=key)
            cached = await cache.get_one(key)
            if cached is not None:
                return self._schema().model_validate(cached)
            entity = await self._find(user_id=user.id, filters=criteria, required=True)
            result = self._schema().model_validate(entity, from_attributes=True)
            await cache.set_one(key, result)
            return result

    async def _invalidate_cache(
        self, user: User, entity: ModelT, operation: str
    ) -> None:
        if self.schema_class is None:
            return
        try:
            cache = self._cache(user.id)
            parents = [
                self._cache_scope(parent, user.id) for parent in self.parents_alias
            ]
            await cache.delete_with_parent_cache(parents)
        except Exception:
            self.logger_params.logger.warning(
                "Cache invalidation failed for %s after committed %s",
                self.alias,
                operation,
                exc_info=True,
                extra={
                    "service": self.logger_params.service,
                    "operation": operation,
                    "user_request": user.username,
                    "user_id": str(user.id),
                    "target_id": str(entity.id),
                },
            )

    async def _find(
        self, *, user_id: UUID, filters: Mapping[str, object], required: bool
    ) -> ModelT | None:
        entity = await self.repository.find_by(user_id=user_id, filters=filters)
        if entity is None and required:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND, detail=f"{self.alias} not found"
            )
        return entity

    async def find_by(
        self, *, user: User, filters: Mapping[str, object], required: bool = True
    ) -> ModelT | None:
        async with self._operation("find_by", user.username):
            return await self._find(user_id=user.id, filters=filters, required=required)

    async def _get(self, identifier: UUID | str, user: User) -> ModelT:
        entity = await self._find(
            user_id=user.id, filters={"id": identifier}, required=True
        )
        assert entity is not None
        return entity

    @staticmethod
    def _write_data(payload: BaseModel, *, partial: bool) -> dict[str, object]:
        data = payload.model_dump(exclude_unset=partial)
        managed = _MANAGED_FIELDS.intersection(data)
        if managed:
            raise HTTPException(
                status_code=HTTPStatus.UNPROCESSABLE_CONTENT,
                detail=f"Server-managed fields cannot be supplied: {sorted(managed)}",
            )
        return data

    @abstractmethod
    def _build_entity(self, user_id: UUID, data: dict[str, object]) -> ModelT:
        raise NotImplementedError

    async def _normalize(
        self, data: dict[str, object], user: User, entity_id: UUID | None = None
    ) -> dict[str, object]:
        return data

    async def _prepare_create(
        self, data: dict[str, object], user: User
    ) -> dict[str, object]:
        return await self._normalize(data, user)

    async def _prepare_update(
        self, entity: ModelT, data: dict[str, object], user: User
    ) -> dict[str, object]:
        return await self._normalize(data, user, entity_id=cast(UUID, entity.id))

    async def create(self, user: User, payload: CreateT) -> ModelT:
        async with self._operation("create", user.username):
            return await self._create(user, payload)

    async def _create(self, user: User, payload: CreateT) -> ModelT:
        async with self.repository.transaction():
            self.repository.require_owner(user.id)
            data = await self._prepare_create(
                self._write_data(payload, partial=False), user
            )
            result = await self.repository.save(
                self._build_entity(user.id, data), user_id=user.id
            )
        await self._invalidate_cache(user, result, "create")
        return result

    async def update(
        self, identifier: UUID | str, payload: UpdateT, user: User
    ) -> Message:
        async with self._operation("update", user.username, identifier):
            async with self.repository.transaction():
                entity = await self._get(identifier, user)
                data = await self._prepare_update(
                    entity, self._write_data(payload, partial=True), user
                )
                if _MANAGED_FIELDS.intersection(data):
                    raise ValueError(
                        "An update extension cannot replace managed fields"
                    )
                for field, value in data.items():
                    self.repository._column(field)
                    setattr(entity, field, value)
                await self.repository.update(entity, user_id=user.id)
            await self._invalidate_cache(user, entity, "update")
            return Message(message=f"Update {self.alias} {identifier} successfully")

    async def delete(self, user: User, identifier: UUID | str) -> Message:
        async with self._operation("delete", user.username, identifier):
            async with self.repository.transaction():
                entity = await self._get(identifier, user)
                await self.repository.delete(entity, user_id=user.id)
            await self._invalidate_cache(user, entity, "delete")
            return Message(message=f"Delete {self.alias} {identifier} successfully")
