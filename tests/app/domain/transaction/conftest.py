from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.transaction.schema import TransactionCreateSchema
from app.domain.transaction.service import TransactionService
from app.models import Transaction


@pytest.fixture
def transaction_data():
    return {
        "name": "Monthly payment",
        "value": "125.90",
        "direction": "OUT",
        "account_id": str(uuid4()),
        "expected_on": "2026-11-10",
    }


@pytest.fixture
def transaction_payload(transaction_data):
    return TransactionCreateSchema.model_validate(transaction_data)


@pytest.fixture
def transaction_entity(user, transaction_payload):
    return Transaction(user_id=user.id, **transaction_payload.model_dump())


@pytest.fixture
def transaction_repository(transaction_entity):
    repository = MagicMock()
    repository.find_by = AsyncMock(return_value=transaction_entity)
    repository.list_all = AsyncMock(return_value=[transaction_entity])
    repository.save = AsyncMock(side_effect=lambda entity, **kwargs: entity)
    repository.update = AsyncMock(side_effect=lambda entity, **kwargs: entity)
    repository.delete = AsyncMock()

    @asynccontextmanager
    async def transaction():
        yield

    repository.transaction = MagicMock(side_effect=transaction)
    return repository


@pytest.fixture
def transaction_service(transaction_repository):
    service = TransactionService(transaction_repository)
    service._invalidate_cache = AsyncMock()
    return service


@pytest.fixture
def transaction_session():
    session = MagicMock(spec=AsyncSession)
    session.scalars.return_value = MagicMock()
    session.scalar.return_value = 1
    return session


@pytest.fixture
def transaction_response(transaction_entity):
    return {
        "id": str(transaction_entity.id),
        "name": transaction_entity.name,
        "value": str(transaction_entity.value),
        "direction": "OUT",
        "status": "PENDING",
        "expected_on": transaction_entity.expected_on.isoformat(),
        "created_at": transaction_entity.created_at.isoformat(),
        "account": {
            "id": str(transaction_entity.account_id),
            "name": "Main account",
            "type": "CHECKING",
            "is_active": True,
            "created_at": transaction_entity.created_at.isoformat(),
        },
    }
