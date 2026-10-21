from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ReceiptFieldRule,
    ReceiptIdentificationRule,
    ReceiptInterpretationProfile,
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
    session.scalars.return_value.all.return_value = []
    return session


@pytest.fixture
def rules_repository():
    repository = SimpleNamespace(
        find_by=AsyncMock(return_value=None),
        find_by_code=AsyncMock(return_value=None),
        list_all=AsyncMock(return_value=[]),
        save=AsyncMock(),
        delete=AsyncMock(),
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
