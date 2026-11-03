from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.receipt.repository import ReceiptRepository
from app.models import Receipt, ReceiptStatusEnum
from app.shared.schemas import FilterPage


@pytest.fixture
def session(receipt):
    session = MagicMock(spec=AsyncSession)
    session.begin = AsyncMock()
    session.info = {}
    session.in_transaction.return_value = False
    session.in_nested_transaction.return_value = False
    session.scalar.return_value = receipt.user_id
    session.scalars.return_value = MagicMock()
    return session


@pytest.fixture
def receipt(user):
    return Receipt(
        user_id=user.id,
        file_name="receipt.pdf",
        file_type="application/pdf",
        file_size=7,
        file_hash="file-hash",
        status=ReceiptStatusEnum.RECEIVED,
        data=None,
    )


@pytest.mark.asyncio
async def test_delete_removes_entity_before_transaction_commits(receipt, session):
    repository = ReceiptRepository(session)

    async with repository.transaction():
        await repository.delete(receipt, user_id=receipt.user_id)
        session.commit.assert_not_awaited()

    session.delete.assert_awaited_once_with(receipt)
    session.commit.assert_awaited_once_with()
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_does_not_commit_when_deletion_fails(receipt, session):
    session.delete.side_effect = RuntimeError("delete failed")
    repository = ReceiptRepository(session)

    with pytest.raises(RuntimeError, match="delete failed"):
        async with repository.transaction():
            await repository.delete(receipt, user_id=receipt.user_id)

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["save", "delete"])
async def test_mutations_require_transaction_and_owner(receipt, session, method):
    repo = ReceiptRepository(session)
    with pytest.raises(RuntimeError, match="transaction"):
        await getattr(repo, method)(receipt, user_id=receipt.user_id)
    with pytest.raises(ValueError, match="owner"):
        async with repo.transaction():
            await getattr(repo, method)(receipt, user_id=uuid4())
    session.add.assert_not_called()
    session.delete.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["id", "file_hash"])
async def test_lookup_filters_are_owner_scoped(receipt, session, field):
    session.scalars.return_value.unique.return_value.one_or_none.return_value = receipt
    result = await ReceiptRepository(session).find_by(
        user_id=receipt.user_id, filters={field: getattr(receipt, field)}
    )
    assert result is receipt
    query = session.scalars.await_args.args[0]
    compiled = query.compile(dialect=postgresql.dialect())
    assert "receipts.user_id =" in str(compiled)
    assert receipt.user_id in compiled.params.values()
    assert getattr(receipt, field) in compiled.params.values()


@pytest.mark.asyncio
async def test_pagination_counts_owner_scoped_receipts_and_preserves_filter(
    receipt, session
):
    session.scalar.return_value = 3
    session.scalars.return_value.unique.return_value.all.return_value = [receipt]
    filters = FilterPage(offset=1, limit=1)
    result = await ReceiptRepository(session).list_all(
        user_id=receipt.user_id, page_filter=filters
    )
    assert result.items == [receipt] and result.meta.total == 3
    counted = session.scalar.await_args.args[0].get_final_froms()[0].element
    query = session.scalars.await_args.args[0]
    assert counted.whereclause.compare(query.whereclause)
    assert filters.offset == 1 and filters.limit == 1


@pytest.mark.asyncio
async def test_list_rejects_owner_supplied_as_filter_before_query(receipt, session):
    with pytest.raises(ValueError, match="Unsupported filter: user_id"):
        await ReceiptRepository(session).list_all(
            user_id=receipt.user_id,
            page_filter=FilterPage.build(user_id=uuid4()),
        )
    session.scalars.assert_not_awaited()
