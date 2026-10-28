from uuid import uuid4
from unittest.mock import patch

import pytest

from app.domain.beneficiary.repository import BeneficiaryRepository
from app.models import Beneficiary
from app.shared.schemas import FilterPage

pytestmark = pytest.mark.asyncio


async def test_repository_uses_scoped_queries_and_filtered_pagination(
    beneficiary_session, user
):
    repository = BeneficiaryRepository(beneficiary_session)
    entities = [
        Beneficiary(user_id=user.id, name="Same", name_code="same"),
        Beneficiary(user_id=user.id, name="Other", name_code="other"),
        Beneficiary(user_id=uuid4(), name="Same", name_code="same"),
    ]
    async with repository.transaction():
        for entity in entities:
            await repository.save(entity, user_id=entity.user_id)
    assert (
        await repository.find_by(user_id=user.id, filters={"id": str(entities[0].id)})
        is entities[0]
    )
    assert (
        await repository.find_by(user_id=user.id, filters={"id": str(entities[2].id)})
        is None
    )
    result = await repository.list_all(
        user_id=user.id,
        page_filter=FilterPage.build(name="Same", limit=12, offset=0),
    )
    assert result.items == [entities[0]]
    assert result.meta.total == 1


async def test_delete_requires_transaction_and_commits_at_boundary(
    beneficiary_session, user
):
    repository = BeneficiaryRepository(beneficiary_session)
    entity = Beneficiary(user_id=user.id, name="Delete", name_code="delete")
    async with repository.transaction():
        await repository.save(entity, user_id=user.id)
    identifier = entity.id
    with pytest.raises(RuntimeError, match="transaction"):
        await repository.delete(entity, user_id=user.id)
    with patch.object(
        beneficiary_session, "commit", wraps=beneficiary_session.commit
    ) as commit:
        async with repository.transaction():
            await repository.delete(entity, user_id=user.id)
            commit.assert_not_awaited()
        commit.assert_awaited_once()
    assert await beneficiary_session.get(Beneficiary, identifier) is None
