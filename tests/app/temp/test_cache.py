from types import SimpleNamespace
from datetime import date
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.core.exceptions import handle_service_exception
from app.core.pagination import CustomLimitOffsetPage
from app.shared.schemas import FilterPage
from tests.app.temp.conftest import ItemCreate, ItemSchema, ItemUpdate

pytestmark = pytest.mark.asyncio


async def test_plain_crud_never_initializes_cache(service, user):
    with patch("app.temp.service.CacheService") as cache:
        item = await service.create(user, ItemCreate(name="One"))
        await service.list_all(None, user)
        await service.find_by(user=user, filters={"id": item.id})
        await service.update(item.id, ItemUpdate(name="Two"), user)
        await service.delete(user, item.id)
    cache.assert_not_called()


@pytest.mark.parametrize("method", ["list", "one"])
async def test_cached_methods_without_configuration_fail(service, user, method):
    with pytest.raises(HTTPException) as error:
        if method == "list":
            await service.list_all_cached(None, user)
        else:
            await service.find_one_cached(user=user, filters={"id": uuid4()})
    assert error.value.status_code == 500


@pytest.mark.parametrize("paginated", [False, True])
async def test_list_roundtrip_uses_existing_cache_and_ttl(
    cached_service, records, user, cache_redis, paginated
):
    filters = FilterPage(limit=1, offset=0) if paginated else None
    with patch.object(
        cached_service.repository, "list_all", wraps=cached_service.repository.list_all
    ) as query:
        first = await cached_service.list_all_cached(filters, user)
        second = await cached_service.list_all_cached(filters, user)
        query.assert_awaited_once()
    assert first == second
    if paginated:
        assert isinstance(first, CustomLimitOffsetPage)
        assert first.meta.total == 2
        assert isinstance(first.items[0], ItemSchema)
    else:
        assert isinstance(first[0], ItemSchema)
    assert list(cache_redis.ttls.values()) == [120]


async def test_empty_list_is_a_cache_hit(cached_service, user):
    with patch.object(
        cached_service.repository, "list_all", wraps=cached_service.repository.list_all
    ) as query:
        assert await cached_service.list_all_cached(None, user) == []
        assert await cached_service.list_all_cached(None, user) == []
        query.assert_awaited_once()


async def test_individual_schema_roundtrip_and_case_sensitive_keys(
    cached_service, user, cache_redis
):
    upper = await cached_service.create(user, ItemCreate(name="Case"))
    lower = await cached_service.create(user, ItemCreate(name="case"))
    with patch.object(
        cached_service.repository, "find_by", wraps=cached_service.repository.find_by
    ) as query:
        first = await cached_service.find_one_cached(
            user=user, filters={"name": "Case"}
        )
        assert first.id == upper.id
        assert (
            await cached_service.find_one_cached(user=user, filters={"name": "Case"})
            == first
        )
        assert (
            await cached_service.find_one_cached(user=user, filters={"name": "case"})
        ).id == lower.id
    assert query.await_count == 2
    assert len(cache_redis._data) == 2


async def test_uuid_string_and_uuid_share_lookup_cache(
    cached_service, records, user, cache_redis
):
    identifier = records[0].id
    with patch.object(
        cached_service.repository, "find_by", wraps=cached_service.repository.find_by
    ) as query:
        first = await cached_service.find_one_cached(
            user=user, filters={"id": str(identifier)}
        )
        second = await cached_service.find_one_cached(
            user=user, filters={"id": identifier}
        )
        assert first == second
        assert first.id == identifier
        query.assert_awaited_once()
    assert len(cache_redis._data) == 1
    with patch("app.temp.service.CacheService") as cache, pytest.raises(HTTPException):
        await cached_service.find_one_cached(user=user, filters={"id": "invalid"})
    cache.assert_not_called()


async def test_cache_keys_distinguish_owners_and_all_query_criteria(
    cached_service, records, user, cache_redis
):
    other = SimpleNamespace(id=records[2].user_id, username="other")
    filters = [
        None,
        FilterPage.build(name="Same"),
        FilterPage.build(name="same"),
        FilterPage(limit=1, offset=0),
        FilterPage(limit=1, offset=1),
        FilterPage(limit=2, offset=0),
        FilterPage(order_by="id"),
    ]
    for page in filters:
        await cached_service.list_all_cached(page, user)
    other_items = await cached_service.list_all_cached(None, other)
    assert [item.id for item in other_items] == [records[2].id]
    assert len(cache_redis._data) == 8
    with pytest.raises(HTTPException) as error:
        await cached_service.find_one_cached(user=user, filters={"id": records[2].id})
    assert error.value.status_code == 404


async def test_refresh_scopes_and_does_not_mutate_inputs(
    cached_service, records, user, cache_redis
):
    other = SimpleNamespace(id=records[2].user_id, username="other")
    await cached_service.list_all_cached(None, user)
    await cached_service.list_all_cached(None, other)
    filters = FilterPage(clean_cache=True)
    before = filters.model_dump()
    with patch.object(
        cached_service.repository, "list_all", wraps=cached_service.repository.list_all
    ) as query:
        await cached_service.list_all_cached(filters, user)
        await cached_service.list_all_cached(None, user)
        query.assert_awaited_once()
    assert filters.model_dump() == before
    assert len(cache_redis._data) == 2
    await cached_service.find_one_cached(user=user, filters={"id": records[0].id})
    keys_before = set(cache_redis._data)
    with patch.object(
        cached_service.repository, "find_by", wraps=cached_service.repository.find_by
    ) as query:
        await cached_service.find_one_cached(
            user=user, filters={"id": records[0].id}, clean_cache=True
        )
        await cached_service.find_one_cached(user=user, filters={"id": records[0].id})
        query.assert_awaited_once()
    assert set(cache_redis._data) == keys_before


async def test_cache_distinguishes_direction_relations_and_ranges(
    cached_service, records, user, cache_redis
):
    filters = [
        FilterPage.build(order_by="id", order="asc"),
        FilterPage.build(order_by="id", order="desc"),
        FilterPage.build(child_label="matching"),
        FilterPage.build(start_date=date(2026, 1, 2)),
        FilterPage.build(end_date=date(2026, 1, 1)),
    ]
    with patch.object(
        cached_service.repository, "list_all", wraps=cached_service.repository.list_all
    ) as query:
        results = [await cached_service.list_all_cached(page, user) for page in filters]
        for page, expected in zip(filters, results, strict=True):
            assert await cached_service.list_all_cached(page, user) == expected
        assert query.await_count == len(filters)
    assert len(cache_redis._data) == len(filters)
    assert [item.id for item in results[0]] == list(
        reversed([item.id for item in results[1]])
    )
    assert [item.id for item in results[2]] == [records[0].id]
    assert results[3] == []
    assert len(results[4]) == 2
    with pytest.raises(HTTPException):
        await cached_service.list_all_cached(FilterPage.build(order="invalid"), user)
    assert len(cache_redis._data) == len(filters)


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
async def test_committed_mutation_invalidates_aliases_lists_and_parents_only_for_owner(
    cached_service, user, cache_redis, operation
):
    item = await cached_service.create(user, ItemCreate(name="Before"))
    await cached_service.list_all_cached(None, user)
    await cached_service.find_one_cached(user=user, filters={"name": "Before"})
    parent_key = f"experimental:dashboard:{user.id}:list"
    foreign_key = f"experimental:items:{uuid4()}:list"
    await cache_redis.setex(parent_key, 120, "{}")
    await cache_redis.setex(foreign_key, 120, "{}")
    events = []
    session = cached_service.repository.session
    original_commit, original_scan = session.commit, cache_redis.scan_iter

    async def commit():
        await original_commit()
        events.append("commit")

    async def scan_iter(**kwargs):
        events.append("invalidate")
        async for key in original_scan(**kwargs):
            yield key

    with (
        patch.object(session, "commit", side_effect=commit),
        patch.object(cache_redis, "scan_iter", scan_iter),
    ):
        if operation == "create":
            await cached_service.create(user, ItemCreate(name="New"))
        elif operation == "update":
            await cached_service.update(item.id, ItemUpdate(name="After"), user)
        else:
            await cached_service.delete(user, item.id)
    assert list(cache_redis._data) == [foreign_key]
    assert events[0] == "commit"
    assert events[1:] == ["invalidate", "invalidate"]


async def test_commit_failure_never_invalidates_cache(
    cached_service, user, cache_redis
):
    await cached_service.list_all_cached(None, user)
    original = dict(cache_redis._data)
    with (
        patch.object(
            cached_service.repository.session,
            "commit",
            side_effect=RuntimeError("commit"),
        ),
        pytest.raises(HTTPException),
    ):
        await cached_service.create(user, ItemCreate(name="No"))
    assert cache_redis._data == original
    assert await cached_service.list_all(None, user) == []


async def test_failed_invalidation_warns_but_returns_committed_result(
    cached_service, user, cache_redis
):
    with (
        patch.object(cache_redis, "scan_iter", side_effect=RuntimeError("cache down")),
        patch.object(cached_service.logger_params.logger, "warning") as warning,
    ):
        entity = await cached_service.create(user, ItemCreate(name="Committed"))
    assert entity.id
    assert (
        await cached_service.find_by(user=user, filters={"id": entity.id})
    ).name == "Committed"
    warning.assert_called_once()
    assert warning.call_args.kwargs["extra"]["user_id"] == str(user.id)
    assert warning.call_args.kwargs["extra"]["target_id"] == str(entity.id)


@pytest.mark.parametrize("method", ["list", "one"])
@pytest.mark.parametrize("failure", ["get", "set", "database"])
async def test_cached_failures_have_single_operation_context(
    cached_service, records, user, cache_redis, method, failure
):
    if failure == "database":
        target = cached_service.repository
        attribute = "list_all" if method == "list" else "find_by"
    else:
        target = cache_redis
        attribute = "get" if failure == "get" else "setex"
    with (
        patch.object(
            target, attribute, new=AsyncMock(side_effect=RuntimeError("failure"))
        ),
        patch("app.temp.service.log_service_success") as success,
        patch(
            "app.temp.service.handle_service_exception", wraps=handle_service_exception
        ) as error,
        pytest.raises(HTTPException),
    ):
        if method == "list":
            await cached_service.list_all_cached(None, user)
        else:
            await cached_service.find_one_cached(
                user=user, filters={"id": records[0].id}
            )
    error.assert_called_once()
    success.assert_not_called()
    assert cache_redis._data == {}


async def test_absent_individual_not_cached_and_criteria_checked_before_cache(
    cached_service, user, cache_redis
):
    with pytest.raises(HTTPException) as missing:
        await cached_service.find_one_cached(user=user, filters={"id": uuid4()})
    assert missing.value.status_code == 404
    with patch.object(cache_redis, "get", wraps=cache_redis.get) as get:
        with pytest.raises(HTTPException):
            await cached_service.find_one_cached(user=user, filters={"unknown": "No"})
        with pytest.raises(HTTPException):
            await cached_service.list_all_cached(FilterPage(order_by="bad"), user)
        get.assert_not_awaited()
    assert cache_redis._data == {}
