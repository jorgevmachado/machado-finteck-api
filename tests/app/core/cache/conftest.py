import pytest

from app.core.cache.manager import CacheManager


@pytest.fixture
def manager(redis_client):
    return CacheManager(redis_client=redis_client)
