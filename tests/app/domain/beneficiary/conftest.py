from types import SimpleNamespace
from fnmatch import fnmatchcase
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.cache.manager import CacheManager
from app.core.database.base import table_registry
from app.domain.beneficiary.schema import (
    BeneficiaryCreateSchema,
    BeneficiaryUpdateSchema,
)
from app.domain.beneficiary.service import BeneficiaryService
from app.models import Beneficiary, Payment, utcnow
from tests.conftest import FakeRedis


class BeneficiaryRedis(FakeRedis):
    async def delete(self, key):
        return int(self._data.pop(key, None) is not None)

    async def scan_iter(self, *, match):
        for key in list(self._data):
            if fnmatchcase(key, match):
                yield key


@pytest.fixture
def beneficiary_cache(monkeypatch):
    redis = BeneficiaryRedis()
    manager = CacheManager(redis_client=redis)
    monkeypatch.setattr("app.core.cache.service.CacheManager", lambda: manager)
    return redis


@pytest_asyncio.fixture
async def beneficiary_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: table_registry.metadata.create_all(
                sync, tables=[Beneficiary.__table__, Payment.__table__]
            )
        )
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


@pytest.fixture
def service(beneficiary_session, beneficiary_cache):
    return BeneficiaryService.from_session(beneficiary_session)


@pytest.fixture
def beneficiary():
    return SimpleNamespace(
        id=uuid4(),
        name="Electric Company",
        name_code="electric_company",
        created_at=utcnow(),
        updated_at=None,
        deleted_at=None,
    )


@pytest.fixture
def create_beneficiary_payload():
    return BeneficiaryCreateSchema(name="Electric Company")


@pytest.fixture
def update_beneficiary_payload():
    return BeneficiaryUpdateSchema(name="Water Company")
