from types import SimpleNamespace
from fnmatch import fnmatchcase
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.cache.manager import CacheManager
from app.core.database.base import table_registry
from app.domain.payer.service import PayerService
from app.domain.payer.schema import PayerCreateSchema, PayerUpdateSchema
from app.models import Payer, Payment, utcnow
from tests.conftest import FakeRedis


class PayerRedis(FakeRedis):
    async def delete(self, key):
        return int(self._data.pop(key, None) is not None)

    async def scan_iter(self, *, match):
        for key in list(self._data):
            if fnmatchcase(key, match):
                yield key


@pytest.fixture
def payer_cache(monkeypatch):
    redis = PayerRedis()
    manager = CacheManager(redis_client=redis)
    monkeypatch.setattr("app.core.cache.service.CacheManager", lambda: manager)
    return redis


@pytest_asyncio.fixture
async def payer_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: table_registry.metadata.create_all(
                sync, tables=[Payer.__table__, Payment.__table__]
            )
        )
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


@pytest.fixture
def service(payer_session, payer_cache):
    return PayerService.from_session(payer_session)


@pytest.fixture
def payer():
    return SimpleNamespace(
        id=uuid4(),
        name="Electric Company",
        name_code="electric_company",
        created_at=utcnow(),
        updated_at=None,
        deleted_at=None,
    )


@pytest.fixture
def create_payer_payload():
    return PayerCreateSchema(name="Electric Company")


@pytest.fixture
def update_payer_payload():
    return PayerUpdateSchema(name="Water Company")
