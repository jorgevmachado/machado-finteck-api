from uuid import uuid4
from unittest.mock import patch

import pytest

from app.domain.payer.repository import PayerRepository
from app.models import Payer
from app.shared.schemas import FilterPage

pytestmark = pytest.mark.asyncio


async def test_repository_uses_scoped_queries_and_filtered_pagination(
    payer_session, user
):
    repository = PayerRepository(payer_session)
    entities = [
        Payer(user_id=user.id, name="Same", name_code="same"),
        Payer(user_id=user.id, name="Other", name_code="other"),
        Payer(user_id=uuid4(), name="Same", name_code="same"),
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
        user_id=user.id, page_filter=FilterPage.build(name="Same", limit=12, offset=0)
    )
    assert result.items == [entities[0]]
    assert result.meta.total == 1


async def test_delete_requires_transaction_and_commits_at_boundary(payer_session, user):
    repository = PayerRepository(payer_session)
    entity = Payer(user_id=user.id, name="Delete", name_code="delete")
    async with repository.transaction():
        await repository.save(entity, user_id=user.id)
    identifier = entity.id
    with pytest.raises(RuntimeError, match="transaction"):
        await repository.delete(entity, user_id=user.id)
    with patch.object(payer_session, "commit", wraps=payer_session.commit) as commit:
        async with repository.transaction():
            await repository.delete(entity, user_id=user.id)
            commit.assert_not_awaited()
        commit.assert_awaited_once()
    assert await payer_session.get(Payer, identifier) is None
