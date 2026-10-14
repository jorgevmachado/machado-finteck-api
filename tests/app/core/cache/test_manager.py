import pytest
import redis
from unittest.mock import AsyncMock


class TestCacheManagerBuildKey:
    @staticmethod
    def test_cache_manager_build_key_with_no_parts(manager):
        key = manager.build_key("cache")
        assert key == "cache"

    @staticmethod
    def test_build_key_normalizes_with_none_in_parts(manager):
        key = manager.build_key("cache", " By-Name ", " name ", None)
        assert key == "cache:by-name:name"

    @staticmethod
    def test_build_key_returns_prefix_when_parts_are_empty(manager):
        key = manager.build_key("cache", "", "   ")

        assert key == "cache"

    @staticmethod
    def test_build_key_with_dict_part(manager):
        key = manager.build_key("cache", {"name": "Thomas", "order": 25})

        valid_keys = {
            "cache:name=thomas&order=25",
            "cache:order=25&name=thomas",
            "cache:name=Thomas&order=25",
            "cache:order=25&name=Thomas",
        }
        assert key in valid_keys

    @staticmethod
    def test_build_key_with_dict_none_in_part(manager):
        key = manager.build_key("cache", {"change": None})

        assert key == "cache"


class TestCacheGetCache:
    @staticmethod
    @pytest.mark.asyncio
    async def test_set_and_get_cache(redis_client, manager):
        key = manager.build_key("cache", "by-name", "name")
        payload = {"name": "name", "order": 1}

        await manager.set_cache(key, payload, ttl=10)
        result = await manager.get_cache(key)

        assert result == payload

    @staticmethod
    @pytest.mark.asyncio
    async def test_get_cache_returns_none_for_missing_key(redis_client, manager):
        key = manager.build_key("name", "not-exist")

        result = await manager.get_cache(key)

        assert result is None


class TestCacheSetCache:
    @staticmethod
    @pytest.mark.asyncio
    async def test_set_cache_with_zero_ttl(redis_client, manager):
        key = manager.build_key("name", "meta")

        with pytest.raises(redis.exceptions.ResponseError):
            await manager.set_cache(key, {"total": 1302}, ttl=0)

        result = await manager.get_cache(key)

        assert result is None or result == {"total": 1302}


class TestCacheDelete:
    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_cache(redis_client, manager):
        key = manager.build_key("cache", "delete-one")
        manager.redis_client.delete = AsyncMock(return_value=1)

        await manager.delete_cache(key)

        manager.redis_client.delete.assert_awaited_once_with(key)

    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_pattern(redis_client, manager):
        async def scan_iter(match):
            assert match == "cache:pattern*"
            for key in ["cache:pattern:a", "cache:pattern:b"]:
                yield key

        manager.redis_client.scan_iter = scan_iter
        manager.redis_client.delete = AsyncMock(return_value=1)

        await manager.delete_pattern("cache:pattern*")

        assert manager.redis_client.delete.await_count == 2
