from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.domain.transaction.series.schema import TransactionSeriesUpdateSchema
from app.domain.transaction.series.service import TransactionSeriesService

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    ("frequency", "expected"),
    [
        ("WEEK", (2, None, None)),
        ("MONTH", (None, 10, None)),
        ("YEAR", (None, 10, 4)),
    ],
)
async def test_create_normalizes_frequency_fields_before_save(
    series_service, transaction_repository, series_payload, user, frequency, expected
):
    payload = type(series_payload).model_validate(
        series_payload.model_dump()
        | {"frequency_unit": frequency, "week_day": 2, "day_of_month": 10, "month": 4}
    )
    before = payload.model_dump()
    result = await series_service.create(user, payload)
    assert (result.week_day, result.day_of_month, result.month) == expected
    assert result.user_id == user.id
    assert result.start_date == payload.start_date
    assert result.end_date == payload.end_date
    assert result.account_id == payload.account_id
    assert result.installments == 12
    assert payload.model_dump() == before
    transaction_repository.save.assert_awaited_once_with(result, user_id=user.id)
    transaction_repository.transaction.assert_called_once()
    series_service._invalidate_cache.assert_awaited_once_with(user, result, "create")


async def test_partial_update_preserves_schedule(
    series_service, series_entity, transaction_repository, user
):
    result = await series_service.update(
        series_entity.id, TransactionSeriesUpdateSchema(note="Changed"), user
    )
    assert series_entity.note == "Changed"
    assert series_entity.frequency_interval == 1
    assert series_entity.day_of_month == 10
    transaction_repository.update.assert_awaited_once_with(
        series_entity, user_id=user.id
    )
    assert result.message == f"Update TransactionSeries {series_entity.id} successfully"


@pytest.mark.parametrize("operation", ["find_one", "update", "delete"])
async def test_missing_or_foreign_series_returns_not_found(
    series_service, transaction_repository, user, operation
):
    transaction_repository.find_by.return_value = None
    identifier = uuid4()
    with pytest.raises(HTTPException) as caught:
        if operation == "update":
            await series_service.update(
                identifier, TransactionSeriesUpdateSchema(note="No"), user
            )
        elif operation == "delete":
            await series_service.delete(user, identifier)
        else:
            await series_service.find_one(identifier, user)
    assert caught.value.status_code == 404
    transaction_repository.find_by.assert_awaited_once_with(
        user_id=user.id, filters={"id": identifier}
    )
    transaction_repository.update.assert_not_awaited()
    transaction_repository.delete.assert_not_awaited()


async def test_delete_uses_owner_and_invalidates(
    series_service, series_entity, transaction_repository, user
):
    result = await series_service.delete(user, series_entity.id)
    transaction_repository.delete.assert_awaited_once_with(
        series_entity, user_id=user.id
    )
    series_service._invalidate_cache.assert_awaited_once_with(
        user, series_entity, "delete"
    )
    assert result.message == f"Delete TransactionSeries {series_entity.id} successfully"


async def test_failed_creation_does_not_report_success_or_invalidate(
    series_service, transaction_repository, series_payload, user
):
    transaction_repository.save.side_effect = RuntimeError("database unavailable")
    with (
        patch("app.core.service.base.log_service_success") as success,
        pytest.raises(HTTPException) as caught,
    ):
        await series_service.create(user, series_payload)
    assert caught.value.status_code == 500
    success.assert_not_called()
    series_service._invalidate_cache.assert_not_awaited()


async def test_factory_builds_series_repository(transaction_session):
    service = TransactionSeriesService.from_session(transaction_session)
    assert service.repository.session is transaction_session
    assert service.repository.model.__name__ == "TransactionSeries"
