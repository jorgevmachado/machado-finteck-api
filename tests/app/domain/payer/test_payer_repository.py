from unittest.mock import AsyncMock

import pytest

from app.domain.payer.repository import PayerRepository


@pytest.mark.asyncio
async def test_delete_removes_entity_and_commits(payer):
    session = AsyncMock()
    repository = PayerRepository(session)

    await repository.delete(payer)

    session.delete.assert_awaited_once_with(payer)
    session.commit.assert_awaited_once()
