from unittest.mock import patch
from uuid import uuid4

import pytest

from app.domain.account.repository import AccountRepository
from app.models import Account, AccountTypeEnum
from app.shared.schemas import FilterPage

pytestmark = pytest.mark.asyncio


def _account(user_id, name, **overrides):
    return Account(
        user_id=user_id,
        name=name,
        type=AccountTypeEnum.CASH,
        icon=None,
        color=None,
        agency=None,
        description=None,
        account_number=None,
        financial_institution=None,
        is_active=True,
        **overrides,
    )


async def test_repository_uses_scoped_queries_and_filtered_pagination(
    account_session, user
):
    repository = AccountRepository(account_session)
    entities = [
        _account(user.id, "Same"),
        _account(user.id, "Other"),
        _account(uuid4(), "Same"),
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
    account_session, user
):
    repository = AccountRepository(account_session)
    entity = _account(user.id, "Delete")
    async with repository.transaction():
        await repository.save(entity, user_id=user.id)
    identifier = entity.id
    with pytest.raises(RuntimeError, match="transaction"):
        await repository.delete(entity, user_id=user.id)
    with patch.object(
        account_session, "commit", wraps=account_session.commit
    ) as commit:
        async with repository.transaction():
            await repository.delete(entity, user_id=user.id)
            commit.assert_not_awaited()
        commit.assert_awaited_once()
    assert await account_session.get(Account, identifier) is None


async def test_find_by_name_returns_first_duplicate_for_race(account_session, user):
    repository = AccountRepository(account_session)
    entities = [
        _account(user.id, "Dup"),
        _account(user.id, "Dup"),
        _account(uuid4(), "Dup"),
    ]
    async with repository.transaction():
        for entity in entities:
            await repository.save(entity, user_id=entity.user_id)

    found = await repository.find_by_name(user_id=user.id, name="Dup")

    assert found in (entities[0], entities[1])
    assert found.user_id == user.id
