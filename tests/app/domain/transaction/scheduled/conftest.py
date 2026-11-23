from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.domain.transaction.scheduled.schema import ScheduledTransactionCreateSchema
from app.domain.transaction.scheduled.service import ScheduledTransactionService
from app.models import ScheduledTransaction


@pytest.fixture
def scheduled_data():
    return {
        "name": "Scheduled payment",
        "value": "125.90",
        "direction": "OUT",
        "account_id": str(uuid4()),
        "expected_on": "2026-11-10",
        "occurrence_on": "2026-11-10",
        "occurrence_index": 1,
    }


@pytest.fixture
def scheduled_payload(scheduled_data):
    return ScheduledTransactionCreateSchema.model_validate(
        scheduled_data | {"transaction_series_id": str(uuid4())}
    )


@pytest.fixture
def scheduled_entity(user, scheduled_payload):
    return ScheduledTransaction(user_id=user.id, **scheduled_payload.model_dump())


@pytest.fixture
def scheduled_repository(scheduled_entity):
    repository = MagicMock()
    repository.find_by = AsyncMock(return_value=scheduled_entity)
    repository.list_all = AsyncMock(return_value=[scheduled_entity])
    repository.save = AsyncMock(side_effect=lambda entity, **kwargs: entity)
    repository.update = AsyncMock(side_effect=lambda entity, **kwargs: entity)
    repository.delete = AsyncMock()

    @asynccontextmanager
    async def transaction():
        yield

    repository.transaction = MagicMock(side_effect=transaction)
    return repository


@pytest.fixture
def scheduled_service(scheduled_repository):
    service = ScheduledTransactionService(scheduled_repository)
    service._invalidate_cache = AsyncMock()
    return service


@pytest.fixture
def scheduled_response(scheduled_entity, transaction_response, series_response):
    return {
        "id": str(scheduled_entity.id),
        "name": scheduled_entity.name,
        "value": str(scheduled_entity.value),
        "direction": scheduled_entity.direction.value,
        "status": scheduled_entity.status.value,
        "expected_on": scheduled_entity.expected_on.isoformat(),
        "settled_on": None,
        "occurrence_on": scheduled_entity.occurrence_on.isoformat(),
        "occurrence_index": scheduled_entity.occurrence_index,
        "created_at": scheduled_entity.created_at.isoformat(),
        "account": transaction_response["account"],
        "transaction_serie": series_response,
    }
