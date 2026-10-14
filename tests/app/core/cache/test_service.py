import logging
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi_pagination import LimitOffsetPage
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.cache.manager import CacheManager
from app.core.cache.service import CacheService
from app.core.logging import LoggingParams
from app.shared.schemas import FilterPage


class BaseModelSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    value: int


MOCK_ITEM = BaseModelSchema(id="mock_id", name="mock_name", value=42)


@pytest_asyncio.fixture
async def cache_service(redis_client):
    class TestableCacheService(CacheService):
        def __init__(self, logger_params, alias, prefix, redis_client):
            super().__init__(logger_params=logger_params, schema_class=BaseModelSchema)
            self.alias = alias
            self.prefix = prefix
            self.cache = CacheManager(redis_client=redis_client)

    return TestableCacheService(
        logger_params=LoggingParams(
            logger=logging.getLogger(__name__),
            service="cache_service",
            operation="test_cache",
        ),
        redis_client=redis_client,
        alias="test_cache",
        prefix="test_cache",
    )


class TestCacheServiceBuildKeyList:
    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_build_key_list(cache_service):
        page_filter = FilterPage(offset=0, limit=10)
        key = cache_service.build_key_list(page_filter)
        assert key.startswith(f"{cache_service.prefix}:list")


class TestCacheServiceGetList:
    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_get_list_return_none_when_cache_misses(cache_service):
        page_filter = FilterPage(offset=0, limit=10)
        key = cache_service.build_key_list(page_filter)
        result = await cache_service.get_list(key)
        assert result is None

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_set_and_get_list(cache_service):
        list_item = [MOCK_ITEM]
        page_filter = FilterPage(offset=0, limit=10)
        key = cache_service.build_key_list(page_filter)
        await cache_service.set_list(key, list_item)
        result = await cache_service.get_list(key)
        assert isinstance(result, list)
        assert len(result) == len(list_item)

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_get_list_skips_non_dict_entries(cache_service):
        key = "test_cache:list:test"
        total_result = 2
        cached_data = {
            "type": "list",
            "data": [
                {
                    "id": "1",
                    "name": "bulbasaur",
                    "value": 1,
                },
                "not_a_dict",
                {
                    "id": "2",
                    "name": "ivysaur",
                    "value": 2,
                },
            ],
        }
        cache_service.cache.get_cache = AsyncMock(return_value=cached_data)
        result = await cache_service.get_list(key)
        assert isinstance(result, list)
        assert len(result) == total_result
        assert all(isinstance(p, BaseModelSchema) for p in result)

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_get_list_paginate_type(cache_service):
        key = "test_cache:list:paginate"
        page_obj = LimitOffsetPage[BaseModelSchema](
            items=[MOCK_ITEM],
            limit=10,
            offset=0,
            total=1,
        )
        cached_data = {"type": "paginate", "data": page_obj.model_dump(mode="json")}
        cache_service.cache.get_cache = AsyncMock(return_value=cached_data)
        result = await cache_service.get_list(key)
        assert isinstance(result, LimitOffsetPage)
        assert result.total == 1

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_get_list_returns_none_for_invalid_cached_schema(
        cache_service,
    ):
        key = "test_cache:list:custom-paginate"
        cached_data = {
            "type": "custom-paginate",
            "data": {
                "items": [
                    {
                        "id": "1",
                        "name": "bulbasaur",
                    }
                ],
                "meta": {
                    "total": 1,
                    "limit": 10,
                    "offset": 0,
                    "next_page": None,
                    "previous_page": None,
                    "total_pages": 1,
                    "current_page": 1,
                },
            },
        }
        cache_service.cache.get_cache = AsyncMock(return_value=cached_data)

        result = await cache_service.get_list(key)

        assert result is None


class TestCacheServiceSetList:
    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_set_list_paginate(cache_service):
        key = f"{cache_service.prefix}:list:paginate"
        page_obj = LimitOffsetPage[BaseModelSchema](
            items=[MOCK_ITEM],
            limit=10,
            offset=0,
            total=1,
        )

        cache_service.cache.set_cache = AsyncMock(return_value=None)
        result = await cache_service.set_list(key, page_obj)
        assert result is None

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_set_all_list(cache_service):
        key = f"{cache_service.prefix}:list"

        cache_service.cache.set_cache = AsyncMock(return_value=None)
        result = await cache_service.set_list(key, [MOCK_ITEM])
        assert result is None

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_set_all_list_with_ttl(cache_service):
        key = f"{cache_service.prefix}:list"

        cache_service.cache.set_cache = AsyncMock(return_value=None)
        result = await cache_service.set_list(key, [MOCK_ITEM], ttl=400)
        assert result is None

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_set_list_uses_custom_serializer(cache_service):
        key = f"{cache_service.prefix}:list:custom"
        cache_service.cache.set_cache = AsyncMock(return_value=None)

        result = await cache_service.set_list(
            key,
            [MOCK_ITEM],
            result_list_cache_serialize=lambda data: [{"custom": len(data)}],
        )

        assert result is None
        cache_service.cache.set_cache.assert_awaited_once_with(
            key, {"type": "list", "data": [{"custom": 1}]}, cache_service.ttl
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_set_list_handles_validation_error(
        cache_service, monkeypatch
    ):
        key = f"{cache_service.prefix}:list:invalid"
        cache_service.cache.set_cache = AsyncMock(return_value=None)

        def raise_validation_error(_item):
            raise ValidationError.from_exception_data("BaseModelSchema", [])

        monkeypatch.setattr(
            cache_service.schema_class, "model_validate", raise_validation_error
        )

        result = await cache_service.set_list(key, [object()])

        assert result is None
        cache_service.cache.set_cache.assert_awaited_once_with(
            key, {"type": "list", "data": None}, cache_service.ttl
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_set_list_invalid_type(cache_service):
        key = f"{cache_service.prefix}:list"
        invalid_data = object()
        cache_service.cache.set_cache = AsyncMock(return_value=None)
        result = await cache_service.set_list(key, invalid_data)
        assert result is None


class TestCacheServiceBuildKeyOne:
    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_build_key_one(cache_service):
        key = cache_service.build_key_one("one")
        assert key.startswith(f"{cache_service.prefix}:one")


class TestCacheServiceGetOne:
    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_get_one_returns_none_when_cache_misses(
        cache_service,
    ):
        key = "test_cache:name"
        result = await cache_service.get_one(key)
        assert result is None

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_get_one_returns_schema(cache_service):
        key = "test_cache:name"
        await cache_service.set_one(key, MOCK_ITEM)
        result = await cache_service.get_one(key)
        assert isinstance(result, BaseModelSchema)

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_get_one_returns_none_for_invalid_schema(
        cache_service, monkeypatch
    ):
        key = "test_cache:invalid"
        cache_service.cache.get_cache = AsyncMock(return_value={"bad": "payload"})

        def raise_validation_error(_payload):
            raise ValidationError.from_exception_data("BaseModelSchema", [])

        monkeypatch.setattr(
            cache_service.schema_class, "model_validate", raise_validation_error
        )

        result = await cache_service.get_one(key)

        assert result is None


class TestCacheServiceSetOne:
    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_set_one(cache_service):
        key = "test_cache:name"
        cache_service.cache.set_cache = AsyncMock(return_value=None)
        result = await cache_service.set_one(key, MOCK_ITEM)
        assert result is None

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_set_one_with_ttl(cache_service):
        key = "test_cache:name"
        cache_service.cache.set_cache = AsyncMock(return_value=None)
        result = await cache_service.set_one(key, MOCK_ITEM, ttl=300)
        assert result is None

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_set_one_uses_custom_serializer(cache_service):
        key = "test_cache:name:custom"
        cache_service.cache.set_cache = AsyncMock(return_value=None)

        result = await cache_service.set_one(
            key,
            MOCK_ITEM,
            result_list_cache_serialize=lambda data: {"custom": data.id},
        )

        assert result is None
        cache_service.cache.set_cache.assert_awaited_once_with(
            key, {"custom": MOCK_ITEM.id}, cache_service.ttl
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_set_one_handles_validation_error(
        cache_service, monkeypatch
    ):
        key = "test_cache:name:invalid"
        cache_service.cache.set_cache = AsyncMock(return_value=None)

        def raise_validation_error(_payload):
            raise ValidationError.from_exception_data("BaseModelSchema", [])

        monkeypatch.setattr(
            cache_service.schema_class, "model_validate", raise_validation_error
        )

        result = await cache_service.set_one(key, MOCK_ITEM)

        assert result is None
        cache_service.cache.set_cache.assert_awaited_once_with(
            key, None, cache_service.ttl
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_set_one_when_not_received_data(cache_service):
        key = "test_cache:name"
        cache_service.cache.set_cache = AsyncMock(return_value=None)
        result = await cache_service.set_one(key, None)
        assert result is None

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_delete_domain(cache_service):
        cache_service.cache.delete_pattern = AsyncMock(return_value=None)

        result = await cache_service.delete_domain()

        assert result is None
        cache_service.cache.delete_pattern.assert_awaited_once_with("test_cache*")


class TestCacheServiceDeleteCache:
    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_cache_by_key(cache_service):
        cache_service.cache.delete_cache = AsyncMock(return_value=None)

        result = await cache_service.delete_cache(cache_key="test_cache:item:1")

        assert result is None
        cache_service.cache.delete_cache.assert_awaited_once_with("test_cache:item:1")

    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_cache_by_prefix_without_exclusions(cache_service):
        cache_service.cache.delete_pattern = AsyncMock(return_value=None)

        result = await cache_service.delete_cache(prefix="test_cache")

        assert result is None
        cache_service.cache.delete_pattern.assert_awaited_once_with("test_cache*")

    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_cache_uses_self_prefix_when_prefix_is_none(cache_service):
        cache_service.cache.delete_pattern = AsyncMock(return_value=None)

        result = await cache_service.delete_cache()

        assert result is None
        cache_service.cache.delete_pattern.assert_awaited_once_with(
            f"{cache_service.prefix}*"
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_cache_with_without_preserves_protected_keys(cache_service):
        protected_key = "test_cache:item:protected"
        deletable_key = "test_cache:item:deletable"

        async def mock_scan_iter(match):
            for key in [protected_key, deletable_key]:
                yield key

        cache_service.cache.redis_client.scan_iter = mock_scan_iter
        cache_service.cache.delete_cache = AsyncMock(return_value=None)

        result = await cache_service.delete_cache(
            prefix="test_cache",
            without=[protected_key],
        )

        assert result is None
        cache_service.cache.delete_cache.assert_awaited_once_with(deletable_key)

    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_cache_with_without_all_protected(cache_service):
        key1 = "test_cache:item:1"
        key2 = "test_cache:item:2"

        async def mock_scan_iter(match):
            for key in [key1, key2]:
                yield key

        cache_service.cache.redis_client.scan_iter = mock_scan_iter
        cache_service.cache.delete_cache = AsyncMock(return_value=None)

        result = await cache_service.delete_cache(
            prefix="test_cache",
            without=[key1, key2],
        )

        assert result is None
        cache_service.cache.delete_cache.assert_not_awaited()


class TestCacheServiceRawCache:
    @staticmethod
    @pytest.mark.asyncio
    async def test_get_cache_delegates_to_cache_manager(cache_service):
        key = "test_cache:raw:key"
        expected = {"value": 1}
        cache_service.cache.get_cache = AsyncMock(return_value=expected)

        result = await cache_service.get_cache(key)

        assert result == expected
        cache_service.cache.get_cache.assert_awaited_once_with(key)

    @staticmethod
    @pytest.mark.asyncio
    async def test_set_cache_delegates_to_cache_manager_with_default_ttl(cache_service):
        key = "test_cache:raw:key"
        payload = {"value": 1}
        cache_service.cache.set_cache = AsyncMock(return_value=None)

        result = await cache_service.set_cache(key, payload)

        assert result is None
        cache_service.cache.set_cache.assert_awaited_once_with(
            key,
            payload,
            cache_service.ttl,
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_set_cache_delegates_to_cache_manager_with_custom_ttl(cache_service):
        key = "test_cache:raw:key"
        payload = {"value": 1}
        cache_service.cache.set_cache = AsyncMock(return_value=None)

        result = await cache_service.set_cache(key, payload, ttl=30)

        assert result is None
        cache_service.cache.set_cache.assert_awaited_once_with(key, payload, 30)


class TestCacheServiceDeleteWithParent:
    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_delete_with_parent_list_none(cache_service):
        cache_service.cache.delete_pattern = AsyncMock(return_value=None)

        result = await cache_service.delete_with_parent_cache(parents=None)

        assert result is None
        cache_service.cache.delete_pattern.assert_awaited_once_with("test_cache*")

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_service_delete_with_parent_list(cache_service):
        cache_service.cache.delete_pattern = AsyncMock(return_value=None)

        result = await cache_service.delete_with_parent_cache(
            parents=["parent1", "parent2"]
        )

        assert result is None
        assert cache_service.cache.delete_pattern.call_count == 3
