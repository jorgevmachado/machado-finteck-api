from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from app.core.database.base import table_registry
from app.models import (
    ReceiptFieldRule,
    ReceiptIdentificationRule,
    ReceiptInterpretationProfile,
    Role,
    User,
)


@pytest.fixture
def rule_payload():
    return {
        "field_name": "payer",
        "configuration": {
            "strategy": "regex",
            "patterns": [r"Nome: (?P<value>[^\n]+)"],
            "parser": "text",
        },
    }


@pytest.fixture
def profile(user, rule_payload):
    entity = ReceiptInterpretationProfile(
        user_id=user.id, name="Banco", institution_code="BANK"
    )
    entity.field_rules.append(ReceiptFieldRule(profile_id=entity.id, **rule_payload))
    entity.identification_rules.append(
        ReceiptIdentificationRule(profile_id=entity.id, pattern="BANK", weight=100)
    )
    return entity


@pytest.fixture
def rules_session():
    session = MagicMock(spec=AsyncSession)
    session.info = {}
    session.begin = AsyncMock()
    session.in_transaction.return_value = False
    session.in_nested_transaction.return_value = False
    session.scalar.return_value = None
    session.scalars.return_value = MagicMock()
    session.scalars.return_value.unique.return_value = session.scalars.return_value
    session.scalars.return_value.all.return_value = []
    return session


@pytest_asyncio.fixture
async def rules_postgres_session():
    with PostgresContainer("postgres:16-alpine") as container:
        url = make_url(container.get_connection_url()).set(
            drivername="postgresql+psycopg"
        )
        engine = create_async_engine(url)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(
                    table_registry.metadata.create_all,
                    tables=[
                        Role.__table__,
                        User.__table__,
                        ReceiptInterpretationProfile.__table__,
                        ReceiptFieldRule.__table__,
                        ReceiptIdentificationRule.__table__,
                    ],
                )
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                yield session
        finally:
            await engine.dispose()


@pytest.fixture
def rules_repository():
    repository = SimpleNamespace(
        find_by=AsyncMock(return_value=None),
        find_by_code=AsyncMock(return_value=None),
        list_all=AsyncMock(return_value=[]),
        save_profile=AsyncMock(),
        delete_profile=AsyncMock(),
        lock_seed=AsyncMock(),
        committed=False,
        rolled_back=False,
    )

    @asynccontextmanager
    async def transaction():
        try:
            yield
            repository.committed = True
        except BaseException:
            repository.rolled_back = True
            raise

    repository.transaction = transaction
    return repository
