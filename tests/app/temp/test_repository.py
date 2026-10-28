from asyncio import CancelledError
from datetime import date
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.pagination import CustomLimitOffsetPage
from app.shared.schemas import FilterPage
from app.temp import BaseRepository, RangeFilter, RelationFilter
from tests.app.temp.conftest import Child, Item, ItemRepository

pytestmark = pytest.mark.asyncio


async def test_lookup_is_scoped_to_owner(repository, records, user):
    assert (
        await repository.find_by(user_id=user.id, filters={"id": records[0].id})
        is records[0]
    )
    assert (
        await repository.find_by(user_id=user.id, filters={"id": records[2].id}) is None
    )
    assert await repository.find_by(user_id=user.id, filters={"id": uuid4()}) is None


async def test_uuid_strings_are_normalized_without_subclass_override(
    repository, records, user
):
    filters = {"id": str(records[0].id)}
    assert await repository.find_by(user_id=user.id, filters=filters) is records[0]
    assert filters == {"id": str(records[0].id)}
    page_filter = FilterPage.build(**filters, limit=1, offset=0)
    page = await repository.list_all(user_id=user.id, page_filter=page_filter)
    assert page.items == [records[0]]
    assert page.meta.total == 1
    assert page_filter.id == str(records[0].id)
    assert (
        await repository.find_by(user_id=user.id, filters={"id": str(records[2].id)})
        is None
    )


async def test_uuid_normalization_uses_related_and_range_column_types(
    repository, records, user
):
    class RelatedRepository(ItemRepository):
        relation_filters = {"child_id": RelationFilter("children", "id")}
        range_filters = {"min_id": RangeFilter("id", "gte")}

    specialized = RelatedRepository(repository.session)
    child_id = await repository.session.scalar(
        select(Child.id).where(Child.item_id == records[0].id).limit(1)
    )
    assert (
        await specialized.find_by(user_id=user.id, filters={"child_id": str(child_id)})
        is records[0]
    )
    items = await specialized.list_all(
        user_id=user.id, page_filter=FilterPage.build(min_id=str(records[0].id))
    )
    assert {item.id for item in items} == {
        item.id for item in records[:2] if item.id >= records[0].id
    }


async def test_uuid_looking_text_remains_text(repository, user):
    name = str(uuid4())
    async with repository.transaction():
        entity = await repository.save(
            Item(user_id=user.id, name=name), user_id=user.id
        )
    assert await repository.find_by(user_id=user.id, filters={"name": name}) is entity


@pytest.mark.parametrize("method", ["find_by", "list_all"])
async def test_invalid_uuid_fails_before_sql(user, method):
    session = AsyncMock()
    repository = ItemRepository(session)
    with pytest.raises(ValueError):
        if method == "find_by":
            await repository.find_by(user_id=user.id, filters={"id": "invalid"})
        else:
            await repository.list_all(
                user_id=user.id, page_filter=FilterPage.build(id="invalid")
            )
    session.scalars.assert_not_awaited()
    session.scalar.assert_not_awaited()


@pytest.mark.parametrize("filters", [{}, {"unknown": "value"}, {"user_id": uuid4()}])
async def test_lookup_rejects_invalid_criteria_before_sql(filters, user):
    session = AsyncMock()
    with pytest.raises(ValueError):
        await ItemRepository(session).find_by(user_id=user.id, filters=filters)
    session.scalars.assert_not_awaited()


@pytest.mark.parametrize("owner", [None, "", "invalid"])
async def test_missing_owner_fails_before_sql(owner):
    session = AsyncMock()
    repository = ItemRepository(session)
    with pytest.raises(ValueError, match="owner"):
        await repository.list_all(user_id=owner)
    with pytest.raises(ValueError, match="owner"):
        await repository.find_by(user_id=owner, filters={"id": uuid4()})
    session.scalars.assert_not_awaited()


async def test_listing_counts_roots_and_preserves_filters(repository, records, user):
    filters = FilterPage.build(name="Same", limit=1, offset=0, order_by="name")
    before = filters.model_dump()
    page = await repository.list_all(user_id=user.id, page_filter=filters)
    assert isinstance(page, CustomLimitOffsetPage)
    assert page.meta.total == 2
    assert len(page.items) == 1
    assert page.items[0].id == min(item.id for item in records[:2])
    assert filters.model_dump() == before
    items = await repository.list_all(
        user_id=user.id, page_filter=FilterPage.build(name="Same")
    )
    assert len(items) == 2
    empty = await repository.list_all(
        user_id=user.id,
        page_filter=FilterPage.build(name="missing", limit=1, offset=0),
    )
    assert empty.items == []
    assert empty.meta.total == 0
    assert await repository.list_all(user_id=uuid4()) == []


async def test_relation_filter_counts_roots_without_duplicate_pages(
    repository, records, user
):
    repository.session.add(Child(item_id=records[2].id, label="matching"))
    await repository.session.commit()
    filters = FilterPage.build(child_label="matching", limit=1, offset=0)
    page = await repository.list_all(user_id=user.id, page_filter=filters)
    assert page.meta.total == 1
    assert [item.id for item in page.items] == [records[0].id]
    assert len(page.items[0].children) == 2
    next_page = await repository.list_all(
        user_id=user.id, page_filter=filters.with_updates(offset=1)
    )
    assert next_page.meta.total == 1
    assert next_page.items == []
    assert (
        await repository.find_by(user_id=user.id, filters={"child_label": "matching"})
        is records[0]
    )
    assert (
        await repository.list_all(
            user_id=user.id, page_filter=FilterPage.build(child_label="missing")
        )
        == []
    )


async def test_scalar_relation_filter_is_scoped_to_root_owner(session, records, user):
    class ChildRepository(BaseRepository[Child]):
        model = Child
        relation_filters = {"item_name": RelationFilter("item", "name")}

    own = Child(item_id=records[0].id, user_id=user.id)
    foreign = Child(item_id=records[0].id, user_id=uuid4())
    session.add_all([own, foreign])
    await session.commit()
    items = await ChildRepository(session).list_all(
        user_id=user.id, page_filter=FilterPage.build(item_name="Same")
    )
    assert [item.id for item in items] == [own.id]


@pytest.mark.parametrize(
    ("bounds", "expected"),
    [
        ({"start_date": date(2026, 1, 2)}, [1]),
        ({"end_date": date(2026, 1, 1)}, [0]),
        ({"start_date": date(2026, 1, 2), "end_date": date(2026, 1, 2)}, [1]),
        ({"start_date": date(2026, 1, 3), "end_date": date(2026, 1, 1)}, []),
    ],
)
async def test_inclusive_ranges_preserve_owner_and_pagination(
    repository, records, user, bounds, expected
):
    records[1].occurred_on = date(2026, 1, 2)
    await repository.session.commit()
    filters = FilterPage.build(name="Same", limit=10, offset=0, **bounds)
    before = filters.model_dump()
    page = await repository.list_all(user_id=user.id, page_filter=filters)
    assert {item.id for item in page.items} == {records[i].id for i in expected}
    assert page.meta.total == len(expected)
    assert filters.model_dump() == before


async def test_combined_relation_and_range_filters(repository, records, user):
    items = await repository.list_all(
        user_id=user.id,
        page_filter=FilterPage.build(
            child_label="matching",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            name="Same",
        ),
    )
    assert [item.id for item in items] == [records[0].id]


@pytest.mark.parametrize("order", ["asc", "desc"])
async def test_order_direction_applies_to_column_and_stable_tiebreak(
    repository, records, user, order
):
    third = Item(user_id=user.id, name="Z")
    repository.session.add(third)
    await repository.session.commit()
    expected = sorted(
        [*records[:2], third],
        key=lambda item: (item.name, item.id),
        reverse=order == "desc",
    )
    filters = FilterPage.build(order_by="name", order=order)
    items = await repository.list_all(user_id=user.id, page_filter=filters)
    assert [item.id for item in items] == [item.id for item in expected]
    pages = [
        await repository.list_all(
            user_id=user.id, page_filter=filters.with_updates(limit=1, offset=offset)
        )
        for offset in range(3)
    ]
    assert [page.items[0].id for page in pages] == [item.id for item in expected]
    assert all(page.meta.total == 3 for page in pages)


async def test_query_hooks_extend_listing_and_lookup(repository, records, user):
    class RestrictedRepository(ItemRepository):
        def _build_filter(self, query, filters):
            return super()._build_filter(query, filters).where(Item.id == records[1].id)

    specialized = RestrictedRepository(repository.session)
    page = await specialized.list_all(
        user_id=user.id, page_filter=FilterPage(limit=1, offset=0)
    )
    assert page.meta.total == 1
    assert page.items == [records[1]]
    assert (
        await specialized.find_by(user_id=user.id, filters={"id": records[0].id})
        is None
    )


@pytest.mark.parametrize(
    "filters",
    [
        FilterPage.build(misspelled="value"),
        FilterPage(order_by="children.id"),
        FilterPage.build(user_id=uuid4()),
        FilterPage.build(order="invalid"),
        FilterPage.build(order="DESC"),
    ],
)
async def test_listing_rejects_unsupported_fields(filters, user):
    session = AsyncMock()
    with pytest.raises(ValueError):
        await ItemRepository(session).list_all(user_id=user.id, page_filter=filters)
    session.scalars.assert_not_awaited()


@pytest.mark.parametrize(
    "definition",
    [
        RelationFilter("unknown", "name"),
        RelationFilter("name", "name"),
        RelationFilter("children", "unknown"),
        RangeFilter("unknown", "gte"),
        RangeFilter("occurred_on", "invalid"),
    ],
)
async def test_invalid_filter_definitions_fail_before_sql(definition, user):
    class InvalidRepository(ItemRepository):
        relation_filters = (
            {"custom": definition} if isinstance(definition, RelationFilter) else {}
        )
        range_filters = (
            {"custom": definition} if isinstance(definition, RangeFilter) else {}
        )

    session = AsyncMock()
    with pytest.raises(ValueError):
        await InvalidRepository(session).list_all(
            user_id=user.id, page_filter=FilterPage.build(custom="value")
        )
    session.scalars.assert_not_awaited()
    session.scalar.assert_not_awaited()


@pytest.mark.parametrize("autobegin", [False, True])
async def test_transaction_commits_once_and_composes_writes(
    repository, user, autobegin
):
    session = repository.session
    if autobegin:
        await repository.list_all(user_id=user.id)
    with patch.object(session, "commit", wraps=session.commit) as commit:
        async with repository.transaction():
            first = await repository.save(
                Item(user_id=user.id, name="First"), user_id=user.id
            )
            second = await repository.save(
                Item(user_id=user.id, name="Second"), user_id=user.id
            )
            first.name = "Changed"
            await repository.update(first, user_id=user.id)
            await repository.delete(second, user_id=user.id)
            commit.assert_not_awaited()
        commit.assert_awaited_once()
    assert (await repository.list_all(user_id=user.id))[0].name == "Changed"
    assert await session.get(Item, second.id) is None


@pytest.mark.parametrize("method", ["save", "update", "delete"])
async def test_primitives_require_transaction_and_owner(repository, user, method):
    entity = Item(user_id=user.id, name="Name")
    with pytest.raises(RuntimeError, match="inside transaction"):
        await getattr(repository, method)(entity, user_id=user.id)
    with pytest.raises(ValueError, match="owner"):
        async with repository.transaction():
            await getattr(repository, method)(entity, user_id=uuid4())


@pytest.mark.parametrize("method", ["update", "delete", "save"])
async def test_forged_owner_is_checked_against_database(
    repository, records, user, method
):
    foreign_id = records[2].id
    records[2].user_id = user.id
    with pytest.raises(ValueError, match="Stored entity"):
        async with repository.transaction():
            await getattr(repository, method)(records[2], user_id=user.id)
    assert await repository.find_by(user_id=user.id, filters={"id": foreign_id}) is None


@pytest.mark.parametrize("boundary", ["same", "other", "savepoint"])
async def test_nested_boundaries_rejected(repository, boundary):
    session = repository.session
    with pytest.raises(RuntimeError, match="Nested"):
        if boundary == "savepoint":
            async with session.begin_nested():
                async with repository.transaction():
                    pytest.fail("Savepoint must not be adopted")
        else:
            async with repository.transaction():
                other = repository if boundary == "same" else ItemRepository(session)
                async with other.transaction():
                    pytest.fail("Nested transaction must not start")
    assert not session.info


@pytest.mark.parametrize("failure", ["validation", "flush", "commit", "cancel"])
async def test_failure_rolls_back_all_writes(repository, user, failure):
    session = repository.session
    error = (
        CancelledError
        if failure == "cancel"
        else (IntegrityError if failure == "flush" else RuntimeError)
    )
    with pytest.raises(error):
        with (
            patch.object(session, "commit", side_effect=RuntimeError("commit failed"))
            if failure == "commit"
            else patch.object(session, "commit", wraps=session.commit)
        ):
            async with repository.transaction():
                await repository.save(
                    Item(user_id=user.id, name="First", name_code="unique"),
                    user_id=user.id,
                )
                if failure == "validation":
                    raise RuntimeError("validation failed")
                if failure == "cancel":
                    raise CancelledError()
                await repository.save(
                    Item(
                        user_id=user.id,
                        name="Second",
                        name_code="unique" if failure == "flush" else "other",
                    ),
                    user_id=user.id,
                )
    assert (await session.scalars(select(Item))).all() == []
    assert not session.info


async def test_rollback_failure_keeps_original_cause(repository):
    session = repository.session
    with (
        patch.object(session, "commit", side_effect=RuntimeError("commit failed")),
        patch.object(session, "rollback", side_effect=RuntimeError("connection lost")),
        patch("app.temp.repository.logger.exception") as log,
        pytest.raises(RuntimeError, match="commit failed"),
    ):
        async with repository.transaction():
            pass
    log.assert_called_once_with("Failed to roll back experimental transaction")
    assert not session.info
