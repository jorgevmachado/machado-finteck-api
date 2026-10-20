from unittest.mock import AsyncMock

import pytest

from app.domain.institution.repository import InstitutionRepository


@pytest.mark.asyncio
async def test_delete_removes_entity_and_commits(institution):
    session = AsyncMock()
    repository = InstitutionRepository(session)

    await repository.delete(institution)

    session.delete.assert_awaited_once_with(institution)
    session.commit.assert_awaited_once()
