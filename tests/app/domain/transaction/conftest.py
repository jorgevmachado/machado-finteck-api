from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.transaction.schema import TransactionCreateSchema
from app.domain.transaction.service import TransactionService
from app.domain.transaction.series.schema import TransactionSeriesCreateSchema
from app.domain.transaction.series.service import TransactionSeriesService
from app.models import Transaction, TransactionSeries


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


@pytest.fixture
def series_payload():
    return TransactionSeriesCreateSchema(
        kind="CLOSED",
        name="Subscription",
        value="39.90",
        direction="OUT",
        account_id=uuid4(),
        start_date="2026-01-10",
        end_date="2026-12-10",
        frequency_unit="MONTH",
        frequency_interval=1,
        day_of_month=10,
        installments=12,
    )


@pytest.fixture
def series_entity(user, series_payload):
    return TransactionSeries(user_id=user.id, **series_payload.model_dump())


@pytest.fixture
def series_service(transaction_repository, series_entity):
    transaction_repository.find_by.return_value = series_entity
    transaction_repository.list_all.return_value = [series_entity]
    service = TransactionSeriesService(transaction_repository)
    service._invalidate_cache = AsyncMock()
    return service


@pytest.fixture
def series_response(series_entity):
    return {
        "id": str(series_entity.id),
        "name": series_entity.name,
        "kind": "CLOSED",
        "value": "39.90",
        "direction": "OUT",
        "start_date": "2026-01-10",
        "end_date": "2026-12-10",
        "frequency_unit": "MONTH",
        "frequency_interval": 1,
        "day_of_month": 10,
        "installments": 12,
        "created_at": series_entity.created_at.isoformat(),
        "account": {
            "id": str(series_entity.account_id),
            "name": "Main account",
            "type": "CHECKING",
            "is_active": True,
            "created_at": series_entity.created_at.isoformat(),
        },
    }
