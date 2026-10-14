import pytest

import app.core.cache.redis as core_redis


@pytest.mark.asyncio
async def test_redis_client_fixture_uses_test_container(redis_client):
    assert core_redis.redis_client is redis_client
    assert await redis_client.ping() is True
