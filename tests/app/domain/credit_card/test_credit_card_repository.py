from unittest.mock import AsyncMock

import pytest

from app.domain.credit_card.repository import CreditCardRepository


class TestCreditCardRepository:
    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_removes_entity_and_commits(credit_card):
        session = AsyncMock()
        repository = CreditCardRepository(session)

        await repository.delete(credit_card)

        session.delete.assert_awaited_once_with(credit_card)
        session.commit.assert_awaited_once()
