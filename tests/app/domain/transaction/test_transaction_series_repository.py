from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.domain.transaction.series.repository import TransactionSeriesRepository
from app.shared.schemas import FilterPage

pytestmark = pytest.mark.asyncio


async def test_lookup_scopes_owner_and_loads_related_resources(
    transaction_session, series_entity, user
):
    transaction_session.scalars.return_value.unique.return_value.one_or_none.return_value = series_entity
    repository = TransactionSeriesRepository(transaction_session)
    assert (
        await repository.find_by(user_id=user.id, filters={"id": str(series_entity.id)})
        is series_entity
    )
    query = transaction_session.scalars.await_args.args[0]
    compiled = query.compile(dialect=postgresql.dialect())
    assert "transaction_series.user_id =" in str(compiled)
    assert "transaction_series.id =" in str(compiled)
    assert set(compiled.params.values()) == {user.id, series_entity.id}
    assert {option.path.path[1].key for option in query._with_options} == {
        "account",
        "subcategory",
        "credit_card",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("account_id", uuid4()),
        ("credit_card_id", uuid4()),
        ("subcategory_id", uuid4()),
        ("kind", "CLOSED"),
        ("frequency_unit", "MONTH"),
        ("direction", "OUT"),
    ],
)
async def test_pagination_and_count_share_owner_and_filters(
    transaction_session, user, field, value
):
    transaction_session.scalars.return_value.unique.return_value.all.return_value = []
    filters = FilterPage.build(limit=1, offset=0, **{field: value})
    before = filters.model_dump()
    result = await TransactionSeriesRepository(transaction_session).list_all(
        user_id=user.id, page_filter=filters
    )
    for query in (
        transaction_session.scalar.await_args.args[0],
        transaction_session.scalars.await_args.args[0],
    ):
        compiled = query.compile(dialect=postgresql.dialect())
        assert "transaction_series.user_id =" in str(compiled)
        assert f"transaction_series.{field} =" in str(compiled)
        assert user.id in compiled.params.values()
        assert value in compiled.params.values()
    assert result.meta.total == 1
    assert filters.model_dump() == before


@pytest.mark.parametrize("filters", [{"user_id": uuid4()}, {"unknown": "value"}])
async def test_lookup_rejects_unsupported_filters_before_sql(
    transaction_session, user, filters
):
    with pytest.raises(ValueError, match="Unsupported filter"):
        await TransactionSeriesRepository(transaction_session).find_by(
            user_id=user.id, filters=filters
        )
    transaction_session.scalars.assert_not_awaited()


async def test_save_requires_transaction(transaction_session, series_entity, user):
    transaction_session.info = {}
    with pytest.raises(RuntimeError, match="transaction"):
        await TransactionSeriesRepository(transaction_session).save(
            series_entity, user_id=user.id
        )
    transaction_session.add.assert_not_called()
