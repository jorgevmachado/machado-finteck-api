from typing import Annotated, Optional, Type, TypeVar, Callable

from fastapi import Query
from fastapi_pagination import LimitOffsetPage
from pydantic import BaseModel, ValidationError

from app.core.cache.manager import CacheManager
from app.core.logging import LoggingParams, log_service_exception, log_service_success
from app.core.pagination.schemas import CustomLimitOffsetPage
from app.shared.schemas import FilterPage

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class CacheService:
    def __init__(
        self,
        *,
        alias: str = "default",
        prefix: str = "cache",
        logger_params: LoggingParams,
        schema_class: Type[SchemaT],
        default_ttl: int = 86400,
    ):
        self.alias = alias
        self.prefix = prefix
        self.logger_params = logger_params
        self.schema_class = schema_class
        self.ttl = default_ttl
        self.cache = CacheManager()

    def build_key_list(
        self,
        page_filter: Annotated[FilterPage, Query()] = None,
    ):
        filter_page = FilterPage.build(page_filter)
        log_service_success(
            self.logger_params,
            operation="cache_build_key_list",
            message=f"The {self.alias} list cache key was successfully created.",
        )
        return self.cache.build_key(self.prefix, "list", filter_page.model_dump())

    async def get_list(
        self, key: str
    ) -> (
        list[SchemaT] | LimitOffsetPage[SchemaT] | CustomLimitOffsetPage[SchemaT] | None
    ):
        cached = await self.cache.get_cache(key)
        try:
            if cached and "type" in cached and cached["type"] == "list":
                list_deserialized: list[SchemaT] = []
                for item in cached["data"]:
                    if not isinstance(item, dict):
                        continue
                    list_deserialized.append(self.schema_class.model_validate(item))
                log_service_success(
                    self.logger_params,
                    operation="cache_get_list",
                    message=f"List of {self.alias} stored in cache.",
                )
                return list_deserialized
            if cached and "type" in cached and cached["type"] == "paginate":
                log_service_success(
                    self.logger_params,
                    operation="cache_get_list",
                    message=f"Paginated list of cached {self.alias}",
                )
                return LimitOffsetPage[self.schema_class].model_validate(cached["data"])
            if cached and "type" in cached and cached["type"] == "custom-paginate":
                log_service_success(
                    self.logger_params,
                    operation="cache_get_list",
                    message=f"Custom paginated list of cached {self.alias}",
                )
                return CustomLimitOffsetPage[self.schema_class].model_validate(
                    cached["data"]
                )
        except ValidationError:
            log_service_exception(
                self.logger_params,
                operation="cache_get_list",
                message=f"Cached {self.alias} data is invalid for the current schema. Ignoring cache.",
            )
            return None
        log_service_success(
            self.logger_params,
            operation="cache_get_list",
            message=f"No {self.alias} data is cached.",
        )

        return None

    async def set_list(
        self,
        key: str,
        data: list[SchemaT] | LimitOffsetPage[SchemaT] | CustomLimitOffsetPage[SchemaT],
        result_list_cache_serialize: Callable[
            [list[SchemaT] | LimitOffsetPage[SchemaT] | CustomLimitOffsetPage[SchemaT]],
            dict | None,
        ]
        | None = None,
        ttl: Optional[int] = None,
    ) -> None:
        cache_ttl = ttl or self.ttl
        if isinstance(data, list):
            try:
                list_serialized = [
                    self.schema_class.model_validate(item).model_dump(mode="json")
                    for item in data
                ]
            except ValidationError:
                list_serialized = None

            if result_list_cache_serialize:
                list_serialized = result_list_cache_serialize(data)

            await self.cache.set_cache(
                key, {"type": "list", "data": list_serialized}, cache_ttl
            )
            log_service_success(
                self.logger_params,
                operation="cache_set_list",
                message=f"List of {self.alias} successfully cached.",
            )
            return None
        if isinstance(data, LimitOffsetPage):
            list_serialized = (
                LimitOffsetPage[self.schema_class]
                .model_validate(data)
                .model_dump(mode="json")
            )
            await self.cache.set_cache(
                key, {"type": "paginate", "data": list_serialized}, cache_ttl
            )
            log_service_success(
                self.logger_params,
                operation="cache_set_list",
                message=f"Paginated list of {self.alias} successfully cached.",
            )
            return None
        if isinstance(data, CustomLimitOffsetPage):
            list_serialized = (
                CustomLimitOffsetPage[self.schema_class]
                .model_validate(data)
                .model_dump(mode="json")
            )
            await self.cache.set_cache(
                key, {"type": "custom-paginate", "data": list_serialized}, cache_ttl
            )
            log_service_success(
                self.logger_params,
                operation="cache_set_list",
                message=f"Custom paginated list of {self.alias} successfully cached.",
            )
            return None

        log_service_success(
            self.logger_params,
            operation="cache_set_list",
            message=f"No {self.alias} data was cached.",
        )
        return None

    def build_key_one(self, param: str) -> str:
        log_service_success(
            self.logger_params,
            operation="cache_build_key_one",
            message=f"The {self.alias} single item cache key was successfully created.",
        )
        return self.cache.build_key(self.prefix, param)

    async def get_one(
        self,
        key: str,
    ) -> SchemaT | None:
        cached = await self.cache.get_cache(key)
        if cached:
            log_service_success(
                self.logger_params,
                operation="cache_get_one",
                message=f"{self.alias} {key} stored in cache",
            )
            try:
                serialized = self.schema_class.model_validate(cached)
            except ValidationError:
                serialized = None
            return serialized
        log_service_success(
            self.logger_params,
            operation="cache_get_one",
            message=f"No {self.alias} {key} data is cached.",
        )
        return None

    async def set_one(
        self,
        key: str,
        data: Optional[SchemaT] = None,
        result_list_cache_serialize: Callable[[SchemaT], dict] | None = None,
        ttl: Optional[int] = None,
    ) -> None:
        cache_ttl = ttl or self.ttl
        if not data:
            log_service_exception(
                self.logger_params,
                operation="cache_set_one",
                message=f"{self.alias} {key} not provided for caching",
            )
            return None
        try:
            serialized = self.schema_class.model_validate(data).model_dump(mode="json")
        except ValidationError:
            serialized = None
        if result_list_cache_serialize:
            serialized = result_list_cache_serialize(data)
        await self.cache.set_cache(key, serialized, cache_ttl)
        log_service_success(
            self.logger_params,
            operation="cache_set_one",
            message=f"{self.alias} {key} successfully cached.",
        )
        return None

    async def delete_domain(self) -> None:
        pattern = f"{self.prefix}*"
        await self.cache.delete_pattern(pattern)
        log_service_success(
            self.logger_params,
            operation="cache_delete_domain",
            message=f'{self.alias} all keys matching "{pattern}" successfully deleted from cache.',
        )
        return None

    async def delete_with_parent_cache(self, parents: list[str] | None = None) -> None:
        await self.delete_domain()
        if not parents:
            return None
        deleted_count = 0
        for parent in parents:
            pattern = f"{parent}*"
            await self.cache.delete_pattern(pattern)
            deleted_count += 1

        log_service_success(
            self.logger_params,
            operation="cache_delete_parent_cache",
            message=f"In total, the caches of {deleted_count} parents were deleted.",
        )
        return None

    async def delete_cache(
        self,
        prefix: str | None = None,
        without: list[str] | None = None,
        cache_key: str | None = None,
    ) -> None:
        if cache_key:
            await self.cache.delete_cache(cache_key)
            log_service_success(
                self.logger_params,
                operation="cache_delete_cache",
                message=f'{self.alias} key "{cache_key}" successfully deleted from cache.',
            )
            return None

        if prefix is None:
            prefix = self.prefix
        pattern = f"{prefix}*"
        protected_keys = {key for key in (without or []) if key}

        if not protected_keys:
            await self.cache.delete_pattern(pattern)
            log_service_success(
                self.logger_params,
                operation="cache_delete_cache",
                message=f'{self.alias} all keys matching "{pattern}" successfully deleted from cache.',
            )
            return None

        deleted_count = 0
        async for key in self.cache.redis_client.scan_iter(match=pattern):
            if key in protected_keys:
                continue

            await self.cache.delete_cache(key)
            deleted_count += 1

        log_service_success(
            self.logger_params,
            operation="cache_delete_cache",
            message=(
                f'{self.alias} selective cache clear finished for "{pattern}": '
                f"deleted={deleted_count}, protected={len(protected_keys)}."
            ),
        )
        return None

    async def get_cache(self, key: str) -> dict | None:
        log_service_success(
            self.logger_params,
            operation="cache_get_cache",
            message=f"Cache data for {self.alias} with key {key} retrieved.",
        )
        return await self.cache.get_cache(key)

    async def set_cache(self, key: str, data: dict, ttl: Optional[int] = None) -> None:
        cache_ttl = ttl or self.ttl
        await self.cache.set_cache(key, data, cache_ttl)
        log_service_success(
            self.logger_params,
            operation="cache_set_cache",
            message=f"Cache data for {self.alias} with key {key} successfully set.",
        )
        return None
