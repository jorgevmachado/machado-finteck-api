from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.domain.transaction.scheduled.repository import ScheduledTransactionRepository
from app.models import TransactionStatusEnum
from app.shared.schemas import FilterPage

pytestmark = pytest.mark.asyncio


async def test_lookup_scopes_owner_and_loads_related_resources(
    transaction_session, scheduled_entity, user
):
    transaction_session.scalars.return_value.unique.return_value.one_or_none.return_value = (
        scheduled_entity
    )
    repository = ScheduledTransactionRepository(transaction_session)
    result = await repository.find_by(
        user_id=user.id,
        filters={
            "id": str(scheduled_entity.id),
            "transaction_series_id": str(scheduled_entity.transaction_series_id),
        },
    )
    assert result is scheduled_entity
    query = transaction_session.scalars.await_args.args[0]
    compiled = query.compile(dialect=postgresql.dialect())
    assert "scheduled_transactions.user_id =" in str(compiled)
    assert "scheduled_transactions.id =" in str(compiled)
    assert "scheduled_transactions.transaction_series_id =" in str(compiled)
    assert set(compiled.params.values()) == {
        user.id,
        scheduled_entity.id,
        scheduled_entity.transaction_series_id,
    }
    assert {option.path.path[1].key for option in query._with_options} == {
        "account",
        "subcategory",
        "credit_card",
        "transaction_serie",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("account_id", uuid4()),
        ("subcategory_id", uuid4()),
        ("credit_card_id", uuid4()),
        ("transaction_series_id", uuid4()),
        ("direction", "OUT"),
        ("status", TransactionStatusEnum.SETTLED),
    ],
)
async def test_pagination_and_count_share_owner_and_filters(
    transaction_session, user, field, value
):
    transaction_session.scalars.return_value.unique.return_value.all.return_value = []
    filters = FilterPage.build(limit=1, offset=0, **{field: value})
    before = filters.model_dump()
    page = await ScheduledTransactionRepository(transaction_session).list_all(
        user_id=user.id, page_filter=filters
    )
    for query in (
        transaction_session.scalar.await_args.args[0],
        transaction_session.scalars.await_args.args[0],
    ):
        compiled = query.compile(dialect=postgresql.dialect())
        assert "scheduled_transactions.user_id =" in str(compiled)
        assert f"scheduled_transactions.{field} =" in str(compiled)
        assert user.id in compiled.params.values()
        assert value in compiled.params.values()
    assert page.meta.total == 1
    assert filters.model_dump() == before


@pytest.mark.parametrize("filters", [{"user_id": uuid4()}, {"unknown": "value"}])
async def test_lookup_rejects_unsupported_filters_before_sql(
    transaction_session, user, filters
):
    with pytest.raises(ValueError, match="Unsupported filter"):
        await ScheduledTransactionRepository(transaction_session).find_by(
            user_id=user.id, filters=filters
        )
    transaction_session.scalars.assert_not_awaited()


async def test_save_requires_transaction(transaction_session, scheduled_entity, user):
    transaction_session.info = {}
    with pytest.raises(RuntimeError, match="transaction"):
        await ScheduledTransactionRepository(transaction_session).save(
            scheduled_entity, user_id=user.id
        )
    transaction_session.add.assert_not_called()
