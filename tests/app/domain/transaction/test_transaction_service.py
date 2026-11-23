from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.domain.transaction.schema import TransactionUpdateSchema
from app.domain.transaction.service import TransactionService
from app.models import TransactionStatusEnum

pytestmark = pytest.mark.asyncio


async def test_create_builds_owned_entity_and_invalidates_after_save(
    transaction_service, transaction_repository, transaction_payload, user
):
    result = await transaction_service.create(user, transaction_payload)
    assert result.user_id == user.id
    assert result.account_id == transaction_payload.account_id
    assert result.value == Decimal("125.90")
    assert result.status == TransactionStatusEnum.PENDING
    assert result.credit_card_id is None
    assert result.subcategory_id is None
    transaction_repository.save.assert_awaited_once_with(result, user_id=user.id)
    transaction_repository.transaction.assert_called_once()
    transaction_service._invalidate_cache.assert_awaited_once_with(
        user, result, "create"
    )


async def test_build_entity_requires_settled_on_for_settled_transaction(
    transaction_service, transaction_payload, user
):
    data = {
        **transaction_payload.model_dump(),
        "status": TransactionStatusEnum.SETTLED,
    }

    with pytest.raises(
        ValueError, match="settled_on is required when status is SETTLED"
    ):
        transaction_service._build_entity(user.id, data)


async def test_build_entity_preserves_settled_on_for_settled_transaction(
    transaction_service, transaction_payload, user
):
    settled_on = date(2026, 11, 9)
    data = {
        **transaction_payload.model_dump(),
        "status": TransactionStatusEnum.SETTLED,
        "settled_on": settled_on,
    }

    result = transaction_service._build_entity(user.id, data)

    assert result.user_id == user.id
    assert result.status == TransactionStatusEnum.SETTLED
    assert result.settled_on == settled_on


async def test_build_entity_clears_settled_on_for_non_settled_transaction(
    transaction_service, transaction_payload, user
):
    data = {
        **transaction_payload.model_dump(),
        "status": TransactionStatusEnum.PENDING,
        "settled_on": date(2026, 11, 9),
    }

    result = transaction_service._build_entity(user.id, data)

    assert result.status == TransactionStatusEnum.PENDING
    assert result.settled_on is None


async def test_partial_update_changes_only_requested_fields(
    transaction_service, transaction_repository, transaction_entity, user
):
    transaction_entity.status = TransactionStatusEnum.SETTLED
    result = await transaction_service.update(
        transaction_entity.id, TransactionUpdateSchema(note="Changed"), user
    )
    assert transaction_entity.note == "Changed"
    assert transaction_entity.status == TransactionStatusEnum.SETTLED
    assert transaction_entity.value == Decimal("125.90")
    transaction_repository.find_by.assert_awaited_once_with(
        user_id=user.id, filters={"id": transaction_entity.id}
    )
    transaction_repository.update.assert_awaited_once_with(
        transaction_entity, user_id=user.id
    )
    assert result.message == f"Update Transaction {transaction_entity.id} successfully"


@pytest.mark.parametrize("operation", ["find_one", "update", "delete"])
async def test_missing_or_foreign_transaction_returns_404(
    transaction_service, transaction_repository, user, operation
):
    transaction_repository.find_by.return_value = None
    identifier = uuid4()
    with pytest.raises(HTTPException) as caught:
        if operation == "update":
            await transaction_service.update(
                identifier, TransactionUpdateSchema(note="No"), user
            )
        elif operation == "delete":
            await transaction_service.delete(user, identifier)
        else:
            await transaction_service.find_one(identifier, user)
    assert caught.value.status_code == 404
    transaction_repository.find_by.assert_awaited_once_with(
        user_id=user.id, filters={"id": identifier}
    )
    transaction_repository.update.assert_not_awaited()
    transaction_repository.delete.assert_not_awaited()


async def test_delete_uses_trusted_owner_and_invalidates_cache(
    transaction_service, transaction_repository, transaction_entity, user
):
    result = await transaction_service.delete(user, transaction_entity.id)
    transaction_repository.delete.assert_awaited_once_with(
        transaction_entity, user_id=user.id
    )
    transaction_service._invalidate_cache.assert_awaited_once_with(
        user, transaction_entity, "delete"
    )
    assert result.message == f"Delete Transaction {transaction_entity.id} successfully"


async def test_write_failure_is_not_logged_as_success(
    transaction_service, transaction_repository, transaction_payload, user
):
    transaction_repository.save.side_effect = RuntimeError("database unavailable")
    with (
        patch("app.core.service.base.log_service_success") as success,
        pytest.raises(HTTPException) as caught,
    ):
        await transaction_service.create(user, transaction_payload)
    assert caught.value.status_code == 500
    success.assert_not_called()
    transaction_service._invalidate_cache.assert_not_awaited()


async def test_factory_uses_transaction_repository(transaction_session):
    service = TransactionService.from_session(transaction_session)
    assert service.repository.session is transaction_session
    assert service.repository.model.__name__ == "Transaction"
