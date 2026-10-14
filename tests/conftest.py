from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime

import pytest
import pytest_asyncio
import redis
from fastapi.testclient import TestClient
from sqlalchemy import event

os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")

import app.core.cache.redis as core_redis
from app.core.database import get_session
from app.main import app


class FakeSession:
    async def scalar(self, *args, **kwargs):
        return None

    async def execute(self, *args, **kwargs):
        return None

    async def commit(self):
        return None

    async def rollback(self):
        return None

    async def refresh(self, *args, **kwargs):
        return None

    def add(self, *args, **kwargs):
        return None


class FakeRedis:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, key: str):
        return self._data.get(key)

    async def setex(self, key: str, ttl: int, value: str):
        if ttl <= 0:
            raise redis.exceptions.ResponseError("invalid expire time in setex")
        self._data[key] = value
        return True

    async def flushdb(self):
        self._data.clear()
        return True

    async def ping(self):
        return True

    async def aclose(self):
        return None


@pytest.fixture
def client():
    fake_session = FakeSession()

    async def get_session_override():
        return fake_session

    app.dependency_overrides[get_session] = get_session_override
    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def redis_client(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(core_redis, "redis_client", client)

    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest_asyncio.fixture(autouse=True)
async def flush_redis(redis_client):
    await redis_client.flushdb()
    yield
    await redis_client.flushdb()


@pytest.fixture
def redis_cache(redis_client):
    yield redis_client


@contextmanager
def _mock_db_time(*, model, time=datetime(2024, 1, 1)):
    def fake_time_handler(mapper, connection, target):
        if hasattr(target, "created_at"):
            target.created_at = time
        if hasattr(target, "updated_at"):
            target.updated_at = time

    event.listen(model, "before_insert", fake_time_handler)

    yield time

    event.remove(model, "before_insert", fake_time_handler)


@pytest.fixture
def mock_db_time():
    return _mock_db_time
