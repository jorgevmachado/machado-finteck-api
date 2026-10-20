from unittest.mock import AsyncMock

import pytest

from app.domain.beneficiary.repository import BeneficiaryRepository


@pytest.mark.asyncio
async def test_delete_removes_entity_and_commits(beneficiary):
    session = AsyncMock()
    repository = BeneficiaryRepository(session)

    await repository.delete(beneficiary)

    session.delete.assert_awaited_once_with(beneficiary)
    session.commit.assert_awaited_once()
