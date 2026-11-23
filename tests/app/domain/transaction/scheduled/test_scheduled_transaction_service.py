from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.domain.transaction.scheduled.schema import (
    ScheduledTransactionRequestUpdateSchema,
)
from app.domain.transaction.scheduled.service import ScheduledTransactionService
from app.models import TransactionStatusEnum

pytestmark = pytest.mark.asyncio


async def test_create_builds_owned_entity_and_invalidates_cache(
    scheduled_service, scheduled_repository, scheduled_payload, user
):
    result = await scheduled_service.create(user, scheduled_payload)
    assert result.user_id == user.id
    assert result.account_id == scheduled_payload.account_id
    assert result.transaction_series_id == scheduled_payload.transaction_series_id
    assert result.value == Decimal("125.90")
    assert result.status == TransactionStatusEnum.PENDING
    scheduled_repository.save.assert_awaited_once_with(result, user_id=user.id)
    scheduled_repository.transaction.assert_called_once()
    scheduled_service._invalidate_cache.assert_awaited_once_with(
        user, result, "create"
    )


async def test_build_entity_requires_settled_on_for_settled_transaction(
    scheduled_service, scheduled_payload, user
):
    data = {
        **scheduled_payload.model_dump(),
        "status": TransactionStatusEnum.SETTLED,
    }
    with pytest.raises(
        ValueError, match="settled_on is required when status is SETTLED"
    ):
        scheduled_service._build_entity(user.id, data)


async def test_build_entity_preserves_settled_on_for_settled_transaction(
    scheduled_service, scheduled_payload, user
):
    settled_on = date(2026, 11, 9)
    data = {
        **scheduled_payload.model_dump(),
        "status": TransactionStatusEnum.SETTLED,
        "settled_on": settled_on,
    }
    result = scheduled_service._build_entity(user.id, data)
    assert result.user_id == user.id
    assert result.status == TransactionStatusEnum.SETTLED
    assert result.settled_on == settled_on


async def test_build_entity_clears_settled_on_for_pending_transaction(
    scheduled_service, scheduled_payload, user
):
    data = {
        **scheduled_payload.model_dump(),
        "status": TransactionStatusEnum.PENDING,
        "settled_on": date(2026, 11, 9),
    }
    result = scheduled_service._build_entity(user.id, data)
    assert result.status == TransactionStatusEnum.PENDING
    assert result.settled_on is None


async def test_delete_scopes_to_series_and_invalidates_cache(
    scheduled_service, scheduled_repository, scheduled_entity, user
):
    result = await scheduled_service.delete_scheduled(
        user, scheduled_entity.id, scheduled_entity.transaction_series_id
    )
    scheduled_repository.find_by.assert_awaited_once_with(
        user_id=user.id,
        filters={
            "id": scheduled_entity.id,
            "transaction_series_id": scheduled_entity.transaction_series_id,
        },
    )
    scheduled_repository.delete.assert_awaited_once_with(
        scheduled_entity, user_id=user.id
    )
    scheduled_service._invalidate_cache.assert_awaited_once_with(
        user, scheduled_entity, "delete"
    )
    assert result.message == (
        f"Delete ScheduledTransaction {scheduled_entity.id} successfully"
    )


async def test_delete_returns_not_found_for_other_series(
    scheduled_service, scheduled_repository, user
):
    scheduled_repository.find_by.return_value = None
    identifier, series_id = uuid4(), uuid4()
    with pytest.raises(HTTPException) as caught:
        await scheduled_service.delete_scheduled(user, identifier, series_id)
    assert caught.value.status_code == 404
    scheduled_repository.find_by.assert_awaited_once_with(
        user_id=user.id,
        filters={"id": identifier, "transaction_series_id": series_id},
    )
    scheduled_repository.delete.assert_not_awaited()
    scheduled_service._invalidate_cache.assert_not_awaited()


async def test_update_scopes_to_owner_and_series_and_preserves_omitted_fields(
    scheduled_service, scheduled_repository, scheduled_entity, user
):
    scheduled_entity.status = TransactionStatusEnum.SETTLED
    scheduled_entity.settled_on = date(2026, 11, 9)
    before = (
        scheduled_entity.transaction_series_id,
        scheduled_entity.value,
        scheduled_entity.status,
        scheduled_entity.settled_on,
        scheduled_entity.occurrence_on,
        scheduled_entity.occurrence_index,
    )
    payload = ScheduledTransactionRequestUpdateSchema(note="Changed")
    result = await scheduled_service.update_scheduled(
        identifier=scheduled_entity.id,
        transaction_series_id=scheduled_entity.transaction_series_id,
        payload=payload,
        user=user,
    )
    scheduled_repository.find_by.assert_awaited_once_with(
        user_id=user.id,
        filters={
            "id": scheduled_entity.id,
            "transaction_series_id": scheduled_entity.transaction_series_id,
        },
    )
    assert scheduled_entity.note == "Changed"
    assert (
        scheduled_entity.transaction_series_id,
        scheduled_entity.value,
        scheduled_entity.status,
        scheduled_entity.settled_on,
        scheduled_entity.occurrence_on,
        scheduled_entity.occurrence_index,
    ) == before
    assert payload.model_dump(exclude_unset=True) == {"note": "Changed"}
    scheduled_repository.transaction.assert_called_once()
    scheduled_repository.update.assert_awaited_once_with(
        scheduled_entity, user_id=user.id
    )
    scheduled_service._invalidate_cache.assert_awaited_once_with(
        user, scheduled_entity, "update"
    )
    assert result.message == (
        f"Update ScheduledTransaction {scheduled_entity.id} successfully"
    )


async def test_update_rejects_other_series_without_mutation_or_cache_invalidation(
    scheduled_service, scheduled_repository, scheduled_entity, user
):
    other_series_id = uuid4()
    original_note = scheduled_entity.note
    scheduled_repository.find_by.return_value = None
    with pytest.raises(HTTPException) as caught:
        await scheduled_service.update_scheduled(
            identifier=scheduled_entity.id,
            transaction_series_id=other_series_id,
            payload=ScheduledTransactionRequestUpdateSchema(note="Changed"),
            user=user,
        )
    assert caught.value.status_code == 404
    scheduled_repository.find_by.assert_awaited_once_with(
        user_id=user.id,
        filters={
            "id": scheduled_entity.id,
            "transaction_series_id": other_series_id,
        },
    )
    assert scheduled_entity.note == original_note
    scheduled_repository.update.assert_not_awaited()
    scheduled_service._invalidate_cache.assert_not_awaited()


async def test_update_can_clear_explicitly_null_optional_field(
    scheduled_service, scheduled_repository, scheduled_entity, user
):
    scheduled_entity.note = "Original note"
    await scheduled_service.update_scheduled(
        identifier=scheduled_entity.id,
        transaction_series_id=scheduled_entity.transaction_series_id,
        payload=ScheduledTransactionRequestUpdateSchema(note=None),
        user=user,
    )
    assert scheduled_entity.note is None
    scheduled_repository._column.assert_called_once_with("note")
    scheduled_repository.update.assert_awaited_once_with(
        scheduled_entity, user_id=user.id
    )


async def test_failed_update_does_not_report_success_or_invalidate_cache(
    scheduled_service, scheduled_repository, scheduled_entity, user
):
    scheduled_repository.update.side_effect = RuntimeError("database unavailable")
    with (
        patch("app.core.service.base.log_service_success") as success,
        pytest.raises(HTTPException) as caught,
    ):
        await scheduled_service.update_scheduled(
            identifier=scheduled_entity.id,
            transaction_series_id=scheduled_entity.transaction_series_id,
            payload=ScheduledTransactionRequestUpdateSchema(note="Changed"),
            user=user,
        )
    assert caught.value.status_code == 500
    success.assert_not_called()
    scheduled_service._invalidate_cache.assert_not_awaited()


async def test_failed_creation_does_not_report_success_or_invalidate(
    scheduled_service, scheduled_repository, scheduled_payload, user
):
    scheduled_repository.save.side_effect = RuntimeError("database unavailable")
    with (
        patch("app.core.service.base.log_service_success") as success,
        pytest.raises(HTTPException) as caught,
    ):
        await scheduled_service.create(user, scheduled_payload)
    assert caught.value.status_code == 500
    success.assert_not_called()
    scheduled_service._invalidate_cache.assert_not_awaited()


async def test_factory_builds_scheduled_repository(transaction_session):
    service = ScheduledTransactionService.from_session(transaction_session)
    assert service.repository.session is transaction_session
    assert service.repository.model.__name__ == "ScheduledTransaction"
