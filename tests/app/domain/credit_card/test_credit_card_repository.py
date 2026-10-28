from uuid import uuid4
from unittest.mock import patch

import pytest

from app.domain.credit_card.repository import CreditCardRepository
from app.models import CreditCard, CreditCardBrandEnum
from app.shared.schemas import FilterPage

pytestmark = pytest.mark.asyncio


def _card(user_id, name):
    return CreditCard(
        user_id=user_id,
        name=name,
        brand=CreditCardBrandEnum.VISA,
        closing_day=15,
        due_day=25,
        description=None,
        last_four_digits=None,
        limit=None,
        color=None,
        icon=None,
    )


async def test_repository_uses_scoped_queries_and_filtered_pagination(
    credit_card_session, user
):
    repository = CreditCardRepository(credit_card_session)
    entities = [
        _card(user.id, "Same"),
        _card(user.id, "Other"),
        _card(uuid4(), "Same"),
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
    credit_card_session, user
):
    repository = CreditCardRepository(credit_card_session)
    entity = _card(user.id, "Delete")
    async with repository.transaction():
        await repository.save(entity, user_id=user.id)
    identifier = entity.id
    with pytest.raises(RuntimeError, match="transaction"):
        await repository.delete(entity, user_id=user.id)
    with patch.object(
        credit_card_session, "commit", wraps=credit_card_session.commit
    ) as commit:
        async with repository.transaction():
            await repository.delete(entity, user_id=user.id)
            commit.assert_not_awaited()
        commit.assert_awaited_once()
    assert await credit_card_session.get(CreditCard, identifier) is None
