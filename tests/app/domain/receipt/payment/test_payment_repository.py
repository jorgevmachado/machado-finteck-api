from unittest.mock import AsyncMock, call

import pytest

from app.domain.receipt.payment.repository import PaymentRepository

pytestmark = pytest.mark.asyncio


async def test_delete_removes_payment_then_commits(payment):
    session = AsyncMock()

    await PaymentRepository(session).delete(payment)

    session.delete.assert_awaited_once_with(payment)
    session.commit.assert_awaited_once_with()
    assert session.mock_calls == [call.delete(payment), call.commit()]


@pytest.mark.parametrize("failed_method", ["delete", "commit"])
async def test_delete_propagates_database_errors(payment, failed_method):
    session = AsyncMock()
    getattr(session, failed_method).side_effect = RuntimeError("database failure")

    with pytest.raises(RuntimeError, match="database failure"):
        await PaymentRepository(session).delete(payment)

    session.delete.assert_awaited_once_with(payment)
    if failed_method == "delete":
        session.commit.assert_not_awaited()
    else:
        session.commit.assert_awaited_once_with()
