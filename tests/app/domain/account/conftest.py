from fnmatch import fnmatchcase
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.cache.manager import CacheManager
from app.core.database.base import table_registry
from app.domain.account.schema import AccountCreateSchema, AccountUpdateSchema
from app.domain.account.service import AccountService
from app.models import Account, utcnow, AccountTypeEnum
from tests.conftest import FakeRedis


class AccountRedis(FakeRedis):
    async def delete(self, key):
        return int(self._data.pop(key, None) is not None)

    async def scan_iter(self, *, match):
        for key in list(self._data):
            if fnmatchcase(key, match):
                yield key


@pytest.fixture
def account_cache(monkeypatch):
    redis = AccountRedis()
    manager = CacheManager(redis_client=redis)
    monkeypatch.setattr("app.core.cache.service.CacheManager", lambda: manager)
    return redis


@pytest_asyncio.fixture
async def account_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: table_registry.metadata.create_all(
                sync, tables=[Account.__table__]
            )
        )
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


@pytest.fixture
def service(account_session, account_cache):
    return AccountService.from_session(account_session)


@pytest.fixture
def account():
    return SimpleNamespace(
        id=uuid4(),
        icon="account",
        type=AccountTypeEnum.CASH,
        name="Test Account",
        color="Purple",
        agency="1234",
        is_active=True,
        description="Description of the test account",
        account_number="123456789",
        financial_institution="Nubank",
        created_at=utcnow(),
        updated_at=None,
        deleted_at=None,
    )


@pytest.fixture
def create_account_payload():
    return AccountCreateSchema(
        icon="account",
        type=AccountTypeEnum.CASH,
        name="Test Account",
        color="Purple",
        agency="1234",
        is_active=True,
        description="Description of the test account",
        account_number="123456789",
        financial_institution="Nubank",
    )


@pytest.fixture
def update_account_payload(create_account_payload):
    return AccountUpdateSchema.model_validate(
        create_account_payload.model_dump(exclude_unset=True)
    )
