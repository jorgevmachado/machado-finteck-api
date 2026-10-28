from types import SimpleNamespace
from fnmatch import fnmatchcase
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.cache.manager import CacheManager
from app.core.database.base import table_registry
from app.domain.credit_card.schema import (
    CreditCardCreateSchema,
    CreditCardUpdateSchema,
)
from app.domain.credit_card.service import CreditCardService
from app.models import CreditCard, utcnow, CreditCardBrandEnum
from tests.conftest import FakeRedis


class CreditCardRedis(FakeRedis):
    async def delete(self, key):
        return int(self._data.pop(key, None) is not None)

    async def scan_iter(self, *, match):
        for key in list(self._data):
            if fnmatchcase(key, match):
                yield key


@pytest.fixture
def credit_card_cache(monkeypatch):
    redis = CreditCardRedis()
    manager = CacheManager(redis_client=redis)
    monkeypatch.setattr("app.core.cache.service.CacheManager", lambda: manager)
    return redis


@pytest_asyncio.fixture
async def credit_card_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: table_registry.metadata.create_all(
                sync, tables=[CreditCard.__table__]
            )
        )
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


@pytest.fixture
def service(credit_card_session, credit_card_cache):
    return CreditCardService.from_session(credit_card_session)


@pytest.fixture
def credit_card():
    return SimpleNamespace(
        id=uuid4(),
        icon="credit_card",
        brand=CreditCardBrandEnum.VISA,
        name="Test Credit Card",
        color="Purple",
        is_active=True,
        description="Description of the test credit card",
        last_four_digits="1234",
        closing_day=15,
        due_day=25,
        limit=5000,
        created_at=utcnow(),
        updated_at=None,
        deleted_at=None,
    )


@pytest.fixture
def create_credit_card_payload():
    return CreditCardCreateSchema(
        icon="credit_card",
        brand=CreditCardBrandEnum.VISA,
        name="Test Credit Card",
        color="Purple",
        is_active=True,
        description="Description of the test credit card",
        last_four_digits="1234",
        closing_day=15,
        due_day=25,
        limit=5000,
    )


@pytest.fixture
def update_credit_card_payload(create_credit_card_payload):
    return CreditCardUpdateSchema.model_validate(
        create_credit_card_payload.model_dump(exclude_unset=True)
    )
