from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.domain.transaction.repository import TransactionRepository
from app.models import TransactionDirectionEnum, TransactionStatusEnum
from app.shared.schemas import FilterPage

pytestmark = pytest.mark.asyncio


def _query(query):
    compiled = query.compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


async def test_lookup_scopes_to_owner_and_loads_relations(
    transaction_session, transaction_entity, user
):
    result = transaction_session.scalars.return_value.unique.return_value
    result.one_or_none.return_value = transaction_entity
    repository = TransactionRepository(transaction_session)
    assert (
        await repository.find_by(
            user_id=user.id, filters={"id": str(transaction_entity.id)}
        )
        is transaction_entity
    )
    query = transaction_session.scalars.await_args.args[0]
    sql, params = _query(query)
    assert "transactions.user_id =" in sql
    assert "transactions.id =" in sql
    assert set(params.values()) == {user.id, transaction_entity.id}
    assert {option.path.path[1].key for option in query._with_options} == {
        "account",
        "subcategory",
        "credit_card",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("account_id", uuid4()),
        ("subcategory_id", uuid4()),
        ("credit_card_id", uuid4()),
        ("direction", TransactionDirectionEnum.IN),
        ("status", TransactionStatusEnum.SETTLED),
    ],
)
async def test_filtered_pagination_counts_same_owned_query(
    transaction_session, user, field, value
):
    transaction_session.scalars.return_value.unique.return_value.all.return_value = []
    repository = TransactionRepository(transaction_session)
    filters = FilterPage.build(limit=1, offset=0, **{field: value})
    before = filters.model_dump()
    page = await repository.list_all(user_id=user.id, page_filter=filters)
    count_sql, count_params = _query(transaction_session.scalar.await_args.args[0])
    items_sql, items_params = _query(transaction_session.scalars.await_args.args[0])
    for sql, params in ((count_sql, count_params), (items_sql, items_params)):
        assert "transactions.user_id =" in sql
        assert f"transactions.{field} =" in sql
        assert user.id in params.values()
        assert value in params.values()
    assert page.meta.total == 1
    assert filters.model_dump() == before


async def test_owner_cannot_be_overridden_by_filter(transaction_session, user):
    with pytest.raises(ValueError, match="Unsupported filter: user_id"):
        await TransactionRepository(transaction_session).find_by(
            user_id=user.id, filters={"user_id": uuid4()}
        )
    transaction_session.scalars.assert_not_awaited()


async def test_save_requires_transaction_before_writing(
    transaction_session, transaction_entity, user
):
    transaction_session.info = {}
    with pytest.raises(RuntimeError, match="transaction"):
        await TransactionRepository(transaction_session).save(
            transaction_entity, user_id=user.id
        )
    transaction_session.add.assert_not_called()


async def test_delete_rejects_foreign_entity_before_sql(
    transaction_session, transaction_entity
):
    repository = TransactionRepository(transaction_session)
    transaction_session.info = {}
    transaction_session.begin = AsyncMock()
    transaction_session.in_transaction.return_value = False
    transaction_session.in_nested_transaction.return_value = False
    with pytest.raises(ValueError, match="trusted owner"):
        async with repository.transaction():
            await repository.delete(transaction_entity, user_id=uuid4())
    transaction_session.scalar.assert_not_awaited()
    transaction_session.delete.assert_not_awaited()
    transaction_session.rollback.assert_awaited_once()
