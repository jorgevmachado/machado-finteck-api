from unittest.mock import AsyncMock, call

import pytest

from app.domain.receipt.repository import ReceiptRepository
from app.models import Receipt, ReceiptStatusEnum


@pytest.fixture
def receipt(user):
    return Receipt(
        user_id=user.id,
        file_name="receipt.pdf",
        file_type="application/pdf",
        file_size=7,
        file_hash="file-hash",
        status=ReceiptStatusEnum.RECEIVED,
        data=None,
    )


@pytest.mark.asyncio
async def test_delete_removes_entity_before_committing(receipt):
    session = AsyncMock()
    repository = ReceiptRepository(session)

    await repository.delete(receipt)

    session.delete.assert_awaited_once_with(receipt)
    session.commit.assert_awaited_once_with()
    assert session.mock_calls == [call.delete(receipt), call.commit()]


@pytest.mark.asyncio
async def test_delete_does_not_commit_when_deletion_fails(receipt):
    session = AsyncMock()
    session.delete.side_effect = RuntimeError("delete failed")
    repository = ReceiptRepository(session)

    with pytest.raises(RuntimeError, match="delete failed"):
        await repository.delete(receipt)

    session.commit.assert_not_awaited()
