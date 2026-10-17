from unittest.mock import AsyncMock

import pytest

from app.domain.account.repository import AccountRepository


class TestAccountRepository:
    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_removes_entity_and_commits(account):
        session = AsyncMock()
        repository = AccountRepository(session)

        await repository.delete(account)

        session.delete.assert_awaited_once_with(account)
        session.commit.assert_awaited_once()
