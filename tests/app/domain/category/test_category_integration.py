from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import FastAPI
import httpx
import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError

from app.core.database import get_session
from app.core.security import get_current_user
from app.core.security.security import create_access_token
from app.domain.category.business import (
    CategoryReconciliationError,
    build_subcategory_reconciliation_plan,
)
from app.domain.category.defaults import load_default_categories
from app.domain.category.repository import CategoryRepository
from app.domain.category.route import router
from app.domain.category.schema import SubcategoryReconcileSchema
from app.models import Category, Role, Subcategory, User
from app.shared.schemas import FilterPage

pytestmark = pytest.mark.integration


async def create_user(session, suffix: str | None = None) -> User:
    suffix = suffix or uuid4().hex
    role = Role(
        name=f"Category test role {suffix}",
        name_code=f"category_test_{suffix}",
        description="Category integration-test role",
    )
    user = User(
        role_id=role.id,
        name=f"Category test user {suffix}",
        email=f"{suffix}@category.test",
        username=f"category-{suffix}",
        date_of_birth=datetime(1990, 1, 1, tzinfo=timezone.utc),
    )
    session.add(role)
    session.add(user)
    await session.commit()
    return user


def category_with_children(user_id, name: str, orders=(1, 2)) -> Category:
    category = Category(
        user_id=user_id,
        name=name,
        icon=None,
        color=None,
        is_active=True,
    )
    category.subcategories.extend(
        Subcategory(name=f"Child {order}", order=order) for order in orders
    )
    return category


async def save_category(session, entity: Category) -> Category:
    repository = CategoryRepository(session)
    async with repository.transaction():
        return await repository.save(entity)


@pytest.mark.asyncio
async def test_http_seed_all_defaults_repeatedly_and_preserve_owner_data(
    category_session_factory,
):
    async with category_session_factory() as session:
        first_user = await create_user(session)
        second_user = await create_user(session)
        custom = category_with_children(second_user.id, "Moradia", (5,))
        custom.icon = "custom-home"
        custom.color = "#112233"
        custom.is_active = False
        await save_category(session, custom)
        custom_id = custom.id
        child_id = custom.subcategories[0].id

    app = FastAPI()
    app.include_router(router, prefix="/categories")
    current_user = first_user

    async def override_session():
        async with category_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: current_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        result = await client.post("/categories/seed")
        assert result.status_code == 200
        assert result.json() == {"created": 14, "skipped": 0}
        initial = (await client.get("/categories")).json()
        assert len(initial) == 14
        assert sum(len(item["subcategories"]) for item in initial) == 59
        by_name = {item["name"]: item for item in initial}
        for payload in load_default_categories():
            item = by_name[payload.name]
            assert (item["icon"], item["color"]) == (payload.icon, payload.color)
            assert item["is_active"] is True
            assert [
                (child["name"], child["icon"], child["color"], child["order"])
                for child in item["subcategories"]
            ] == [
                (child.name, child.icon, child.color, child.order)
                for child in payload.subcategories
            ]
            assert all(child["is_active"] for child in item["subcategories"])
        repeated = await client.post("/categories/seed")
        assert repeated.json() == {"created": 0, "skipped": 14}
        assert (await client.get("/categories")).json() == initial

        current_user = second_user
        result = await client.post("/categories/seed")
        assert result.status_code == 200
        assert result.json() == {"created": 13, "skipped": 1}
        existing = (await client.get(f"/categories/{custom_id}")).json()
        assert existing["icon"] == "custom-home"
        assert existing["color"] == "#112233"
        assert existing["is_active"] is False
        assert existing["updated_at"] is None
        assert len(existing["subcategories"]) == 1
        assert existing["subcategories"][0]["id"] == str(child_id)
        assert existing["subcategories"][0]["order"] == 5
        assert existing["subcategories"][0]["updated_at"] is None
        second_listing = (await client.get("/categories")).json()
        assert len(second_listing) == 14
        assert {item["id"] for item in second_listing}.isdisjoint(
            item["id"] for item in initial
        )
        assert (await client.post("/categories/seed")).json() == {
            "created": 0,
            "skipped": 14,
        }
        deleted = await client.delete(f"/categories/{custom_id}")
        assert deleted.status_code == 200
        replacement = await client.post("/categories/seed")
        assert replacement.json() == {"created": 1, "skipped": 13}
        assert (await client.get(f"/categories/{custom_id}")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("name_conflict", [False, True])
async def test_http_seed_failure_rolls_back_all_flushed_aggregates(
    category_session_factory, monkeypatch, name_conflict
):
    async with category_session_factory() as session:
        user = await create_user(session)
        owner_id = user.id
        sentinel = category_with_children(owner_id, "Preservar")
        await save_category(session, sentinel)
        sentinel_id = sentinel.id

    original_save = CategoryRepository.save
    writes = 0

    async def failing_save(repository, entity, reconciliation=None):
        nonlocal writes
        result = await original_save(repository, entity, reconciliation)
        writes += 1
        if writes == 3:
            if name_conflict:
                await original_save(
                    repository, Category(user_id=owner_id, name=entity.name)
                )
            raise RuntimeError("Failure after flushing three default aggregates")
        return result

    monkeypatch.setattr(CategoryRepository, "save", failing_save)
    app = FastAPI()
    app.include_router(router, prefix="/categories")

    async def override_session():
        async with category_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/categories/seed")
        assert response.status_code == (409 if name_conflict else 500)

    async with category_session_factory() as session:
        roots = (await session.scalars(select(Category))).all()
        assert [root.id for root in roots] == [sentinel_id]
        assert await session.scalar(select(func.count(Subcategory.id))) == 2


@pytest.mark.asyncio
async def test_postgres_constraints_owner_names_and_order_history(
    category_session_factory,
):
    async with category_session_factory() as session:
        owner = await create_user(session)
        other_owner = await create_user(session)
        repository = CategoryRepository(session)
        original = category_with_children(owner.id, "Casa")
        original_id = original.id
        owner_id = owner.id
        await save_category(session, original)
        await save_category(session, category_with_children(owner.id, "casa"))
        await save_category(session, category_with_children(other_owner.id, "Casa"))

        duplicate_name = Category(
            user_id=owner.id, name="Casa", icon=None, color=None, is_active=True
        )
        with pytest.raises(IntegrityError):
            await save_category(session, duplicate_name)

        async with repository.transaction():
            locked = await repository.find_by(
                id=original_id, user_id=owner_id, for_update=True
            )
            await repository.delete(locked)

        replacement = category_with_children(owner_id, "Casa")
        replacement_id = replacement.id
        await save_category(session, replacement)
        assert replacement_id != original_id

        duplicate_child_order = category_with_children(owner_id, "Sem ordem", (1, 1))
        with pytest.raises(IntegrityError):
            await save_category(session, duplicate_child_order)

        async with category_session_factory() as verify_session:
            old = await verify_session.get(Category, original_id)
            current = await verify_session.get(Category, replacement_id)
            assert old.deleted_at is not None
            assert current.deleted_at is None
            assert (
                await verify_session.scalar(
                    select(func.count(Category.id)).where(Category.name == "Sem ordem")
                )
                == 0
            )


@pytest.mark.asyncio
async def test_postgres_allows_order_swap_and_reuses_deleted_order(
    category_session_factory,
):
    async with category_session_factory() as session:
        owner = await create_user(session)
        category = category_with_children(owner.id, "Ordens")
        await save_category(session, category)
        children = list(category.subcategories)
        repository = CategoryRepository(session)

        swapped_payload = [
            SubcategoryReconcileSchema(
                id=children[0].id, name=children[0].name, order=2
            ),
            SubcategoryReconcileSchema(
                id=children[1].id, name=children[1].name, order=1
            ),
        ]
        async with repository.transaction():
            locked = await repository.find_by(
                id=category.id, user_id=owner.id, for_update=True
            )
            plan = build_subcategory_reconciliation_plan(
                swapped_payload, [child.id for child in locked.subcategories]
            )
            await repository.save(locked, reconciliation=plan)

        async with repository.transaction():
            locked = await repository.find_by(
                id=category.id, user_id=owner.id, for_update=True
            )
            old_child = next(
                child for child in locked.subcategories if child.order == 2
            )
            plan = build_subcategory_reconciliation_plan(
                [SubcategoryReconcileSchema(name="Replacement", order=2)],
                [child.id for child in locked.subcategories],
            )
            await repository.save(locked, reconciliation=plan)

        async with category_session_factory() as verify_session:
            persisted = await CategoryRepository(verify_session).find_by(
                id=category.id, user_id=owner.id
            )
            live_children = persisted.subcategories
            assert [(child.name, child.order) for child in live_children] == [
                ("Replacement", 2)
            ]
            removed = await verify_session.get(Subcategory, old_child.id)
            assert removed.deleted_at is not None


@pytest.mark.asyncio
async def test_postgres_rollback_after_partial_root_and_child_flush(
    category_session_factory, monkeypatch
):
    async with category_session_factory() as session:
        owner = await create_user(session)
        category = category_with_children(owner.id, "Original")
        category_id = category.id
        owner_id = owner.id
        await save_category(session, category)
        child_id = category.subcategories[0].id
        repository = CategoryRepository(session)
        real_flush = session.flush

        async def flush_then_fail(*args, **kwargs):
            await real_flush(*args, **kwargs)
            raise RuntimeError("simulated failure after SQL flush")

        monkeypatch.setattr(session, "flush", flush_then_fail)
        with pytest.raises(RuntimeError, match="after SQL flush"):
            async with repository.transaction():
                locked = await repository.find_by(
                    id=category_id, user_id=owner_id, for_update=True
                )
                locked.name = "Uncommitted"
                locked.subcategories[0].name = "Uncommitted child"
                await repository.save(locked)

    async with category_session_factory() as verify_session:
        persisted = await CategoryRepository(verify_session).find_by(
            id=category_id, user_id=owner_id
        )
        assert persisted.name == "Original"
        assert persisted.subcategories[0].id == child_id
        assert persisted.subcategories[0].name == "Child 1"


@pytest.mark.asyncio
async def test_postgres_deferred_constraint_commit_failure_rolls_back_everything(
    category_session_factory,
):
    async with category_session_factory() as session:
        owner = await create_user(session)
        category = category_with_children(owner.id, "Before commit")
        category_id = category.id
        owner_id = owner.id
        await save_category(session, category)
        repository = CategoryRepository(session)

        with pytest.raises(IntegrityError):
            async with repository.transaction():
                locked = await repository.find_by(
                    id=category_id, user_id=owner_id, for_update=True
                )
                locked.name = "After failed commit"
                locked.subcategories[1].order = locked.subcategories[0].order
                await repository.save(locked)

    async with category_session_factory() as verify_session:
        persisted = await CategoryRepository(verify_session).find_by(
            id=category_id, user_id=owner_id
        )
        assert persisted.name == "Before commit"
        assert [child.order for child in persisted.subcategories] == [1, 2]


@pytest.mark.asyncio
async def test_postgres_checks_visual_fields_and_positive_order(
    category_session_factory,
):
    async with category_session_factory() as session:
        owner = await create_user(session)
        owner_id = owner.id
        invalid_color = Category(
            user_id=owner_id,
            name="Invalid color",
            icon=None,
            color="#FFF",
            is_active=True,
        )
        with pytest.raises(IntegrityError):
            await save_category(session, invalid_color)

        category = Category(
            user_id=owner_id,
            name="Invalid order",
            icon=None,
            color=None,
            is_active=True,
        )
        category.subcategories.append(Subcategory(name="Bad order", order=0))
        with pytest.raises(IntegrityError):
            await save_category(session, category)


@pytest.mark.asyncio
async def test_postgres_logical_delete_uses_one_timestamp_and_preserves_history(
    category_session_factory,
):
    async with category_session_factory() as session:
        owner = await create_user(session)
        category = category_with_children(owner.id, "Delete me", (1,))
        historical = Subcategory(name="Already deleted", order=2)
        historical.deleted_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        category.subcategories.append(historical)
        await save_category(session, category)
        category_id = category.id
        historical_id = historical.id
        live_child_id = category.subcategories[0].id

        repository = CategoryRepository(session)
        async with repository.transaction():
            locked = await repository.find_by(
                id=category_id, user_id=owner.id, for_update=True
            )
            await repository.delete(locked)

    async with category_session_factory() as verify_session:
        deleted = await verify_session.get(Category, category_id)
        live_child = await verify_session.get(Subcategory, live_child_id)
        historical_child = await verify_session.get(Subcategory, historical_id)
        assert deleted.is_active is False
        assert live_child.deleted_at == deleted.deleted_at
        assert live_child.is_active is False
        assert historical_child.deleted_at == datetime(2020, 1, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_concurrent_duplicate_names_across_sessions_have_one_winner(
    category_session_factory,
):
    async with category_session_factory() as session:
        owner = await create_user(session)

    async def create_duplicate() -> bool:
        async with category_session_factory() as session:
            try:
                await save_category(
                    session,
                    Category(
                        user_id=owner.id,
                        name="Corrida",
                        icon=None,
                        color=None,
                        is_active=True,
                    ),
                )
                return True
            except IntegrityError:
                return False

    results = await asyncio.gather(create_duplicate(), create_duplicate())
    assert sorted(results) == [False, True]


@pytest.mark.asyncio
async def test_concurrent_mutations_wait_for_lock_and_reload_children(
    category_session_factory,
):
    async with category_session_factory() as session:
        owner = await create_user(session)
        category = category_with_children(owner.id, "Initial")
        await save_category(session, category)

    first_locked = asyncio.Event()
    allow_first_commit = asyncio.Event()
    second_lock_query_started = asyncio.Event()
    second_observed: list[tuple[str, str]] = []
    engine = category_session_factory.kw["bind"]

    def signal_lock_query(_conn, _cursor, statement, *_args):
        if "FOR UPDATE" in statement:
            second_lock_query_started.set()

    async def first_mutation():
        async with category_session_factory() as session:
            repository = CategoryRepository(session)
            async with repository.transaction():
                locked = await repository.find_by(
                    id=category.id, user_id=owner.id, for_update=True
                )
                locked.name = "First commit"
                locked.subcategories[0].name = "First child commit"
                await repository.save(locked)
                first_locked.set()
                await allow_first_commit.wait()

    async def second_mutation():
        await first_locked.wait()
        async with category_session_factory() as session:
            repository = CategoryRepository(session)
            async with repository.transaction():
                locked = await repository.find_by(
                    id=category.id, user_id=owner.id, for_update=True
                )
                second_observed.append((locked.name, locked.subcategories[0].name))
                locked.name = "Second commit"
                await repository.save(locked)

    first_task = asyncio.create_task(first_mutation())
    await first_locked.wait()
    event.listen(engine.sync_engine, "before_cursor_execute", signal_lock_query)
    second_task = asyncio.create_task(second_mutation())
    try:
        await asyncio.wait_for(second_lock_query_started.wait(), timeout=5)
        await asyncio.sleep(0.1)
        assert not second_task.done()
    finally:
        allow_first_commit.set()
        await asyncio.gather(first_task, second_task)
        event.remove(engine.sync_engine, "before_cursor_execute", signal_lock_query)

    assert second_observed == [("First commit", "First child commit")]


@pytest.mark.asyncio
async def test_concurrent_membership_update_rejects_child_removed_by_first_commit(
    category_session_factory,
):
    async with category_session_factory() as session:
        owner = await create_user(session)
        owner_id = owner.id
        category = category_with_children(owner_id, "Membership race", (1,))
        removed_child_id = category.subcategories[0].id
        category_id = category.id
        await save_category(session, category)

    first_locked = asyncio.Event()
    second_lock_query_started = asyncio.Event()
    allow_first_commit = asyncio.Event()
    second_outcome: list[str] = []
    engine = category_session_factory.kw["bind"]

    def signal_lock_query(_conn, _cursor, statement, *_args):
        if "FOR UPDATE" in statement:
            second_lock_query_started.set()

    async def remove_child():
        async with category_session_factory() as session:
            repository = CategoryRepository(session)
            async with repository.transaction():
                aggregate = await repository.find_by(
                    id=category_id, user_id=owner_id, for_update=True
                )
                plan = build_subcategory_reconciliation_plan(
                    [], [child.id for child in aggregate.subcategories]
                )
                await repository.save(aggregate, reconciliation=plan)
                first_locked.set()
                await allow_first_commit.wait()

    async def retain_removed_child():
        await first_locked.wait()
        async with category_session_factory() as session:
            repository = CategoryRepository(session)
            try:
                async with repository.transaction():
                    aggregate = await repository.find_by(
                        id=category_id, user_id=owner_id, for_update=True
                    )
                    plan = build_subcategory_reconciliation_plan(
                        [
                            SubcategoryReconcileSchema(
                                id=removed_child_id,
                                name="Attempt restore",
                                order=1,
                            )
                        ],
                        [child.id for child in aggregate.subcategories],
                    )
                    await repository.save(aggregate, reconciliation=plan)
            except CategoryReconciliationError:
                second_outcome.append("422")

    first_task = asyncio.create_task(remove_child())
    await first_locked.wait()
    event.listen(engine.sync_engine, "before_cursor_execute", signal_lock_query)
    second_task = asyncio.create_task(retain_removed_child())
    try:
        await asyncio.wait_for(second_lock_query_started.wait(), timeout=5)
        await asyncio.sleep(0.1)
        assert not second_task.done()
    finally:
        allow_first_commit.set()
        await asyncio.gather(first_task, second_task)
        event.remove(engine.sync_engine, "before_cursor_execute", signal_lock_query)

    assert second_outcome == ["422"]
    async with category_session_factory() as verify_session:
        category = await CategoryRepository(verify_session).find_by(
            id=category_id, user_id=owner_id
        )
        assert category.subcategories == []
        removed = await verify_session.get(Subcategory, removed_child_id)
        assert removed.deleted_at is not None


@pytest.mark.asyncio
async def test_listing_loads_children_in_batches_and_counts_root_categories(
    category_session_factory,
):
    async with category_session_factory() as session:
        owner = await create_user(session)
        for name in ("One", "Two", "Three"):
            await save_category(session, category_with_children(owner.id, name))

    statements: list[str] = []
    engine = category_session_factory.kw["bind"]

    def capture_statement(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(
        engine.sync_engine,
        "before_cursor_execute",
        capture_statement,
    )
    try:
        async with category_session_factory() as session:
            result = await CategoryRepository(session).list_all(
                # Limit without page/offset deliberately remains a plain list.
                FilterPage.build(user_id=owner.id, limit=12)
            )
            assert len(result) == 3
            assert all(len(category.subcategories) == 2 for category in result)

            paged = await CategoryRepository(session).list_all(
                FilterPage.build(user_id=owner.id, page=1, limit=2)
            )
            assert paged.meta.total == 3
            assert len(paged.items) == 2
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture_statement)

    select_statements = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("SELECT")
    ]
    assert len(select_statements) == 5
    assert "FROM categories" in select_statements[0]
    assert all("FROM payments" not in statement for statement in select_statements)


@pytest.mark.asyncio
async def test_http_create_mixed_and_empty_reconciliation_persists_logically(
    category_session_factory,
):
    async with category_session_factory() as session:
        user = await create_user(session)

    app = FastAPI()
    app.include_router(router, prefix="/categories")

    async def override_session():
        async with category_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created = await client.post(
            "/categories",
            json={
                "name": "Reconciliacao",
                "icon": "house",
                "color": "#123ABC",
                "subcategories": [
                    {
                        "name": "Retido",
                        "icon": "key",
                        "color": "#abcdef",
                        "is_active": False,
                        "order": 1,
                    },
                    {"name": "Removido", "order": 2},
                ],
            },
        )
        assert created.status_code == 201
        created_body = created.json()
        category_id = created_body["id"]
        retained_id, removed_id = [
            child["id"] for child in created_body["subcategories"]
        ]

        initial_read = await client.get(f"/categories/{category_id}")
        assert initial_read.status_code == 200
        assert initial_read.json()["subcategories"][0]["is_active"] is False

        renamed = await client.put(
            f"/categories/{category_id}", json={"name": "Categoria renomeada"}
        )
        assert renamed.status_code == 200
        after_rename = await client.get(f"/categories/{category_id}")
        assert after_rename.json()["name"] == "Categoria renomeada"
        assert (
            after_rename.json()["subcategories"] == initial_read.json()["subcategories"]
        )
        null_list = await client.put(
            f"/categories/{category_id}",
            json={"name": "Nao salvar", "subcategories": None},
        )
        assert null_list.status_code == 422

        invalid_identity = await client.put(
            f"/categories/{category_id}",
            json={
                "subcategories": [
                    {
                        "id": str(uuid4()),
                        "name": "Foreign child",
                        "order": 1,
                    }
                ]
            },
        )
        invalid_order = await client.put(
            f"/categories/{category_id}",
            json={
                "subcategories": [
                    {
                        "id": retained_id,
                        "name": "Retained",
                        "order": 2,
                    },
                    {"name": "Duplicate", "order": 2},
                ]
            },
        )
        assert invalid_identity.status_code == 422
        assert invalid_order.status_code == 422

        mixed = await client.put(
            f"/categories/{category_id}",
            json={
                "icon": None,
                "subcategories": [
                    {
                        "id": retained_id,
                        "name": "Retido atualizado",
                        "order": 2,
                    },
                    {"name": "Novo", "order": 1},
                ],
            },
        )
        assert mixed.status_code == 200

        fetched = await client.get(f"/categories/{category_id}")
        assert fetched.status_code == 200
        fetched_body = fetched.json()
        assert fetched_body["name"] == "Categoria renomeada"
        assert fetched_body["icon"] is None
        assert fetched_body["color"] == "#123ABC"
        assert [
            (child["name"], child["order"], child["is_active"])
            for child in fetched_body["subcategories"]
        ] == [("Novo", 1, True), ("Retido atualizado", 2, True)]
        assert fetched_body["subcategories"][1]["id"] == retained_id
        assert fetched_body["subcategories"][1]["icon"] is None
        assert fetched_body["subcategories"][1]["color"] is None

        empty = await client.put(
            f"/categories/{category_id}",
            json={"subcategories": []},
        )
        assert empty.status_code == 200
        fetched_empty = await client.get(f"/categories/{category_id}")
        assert fetched_empty.status_code == 200
        assert fetched_empty.json()["subcategories"] == []

        deleted_response = await client.delete(f"/categories/{category_id}")
        assert deleted_response.status_code == 200
        assert deleted_response.json()["message"]
        hidden = await client.get(f"/categories/{category_id}")
        assert hidden.status_code == 404

    async with category_session_factory() as verify_session:
        persisted = await verify_session.get(Category, UUID(category_id))
        retained = await verify_session.get(Subcategory, UUID(retained_id))
        removed = await verify_session.get(Subcategory, UUID(removed_id))
        assert persisted.icon is None
        assert persisted.color == "#123ABC"
        assert retained.deleted_at is not None
        assert retained.is_active is False
        assert removed.deleted_at is not None
        assert removed.is_active is False
        assert persisted.deleted_at is not None
        assert persisted.is_active is False

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_async_authentication_and_category_service_share_autobegun_session(
    category_session_factory, monkeypatch
):
    from app.core.security.security import settings as security_settings

    async with category_session_factory() as session:
        user = await create_user(session)

    app = FastAPI()
    app.include_router(router, prefix="/categories")
    sessions_used = []

    async def shared_session_override():
        async with category_session_factory() as session:
            sessions_used.append(session)
            yield session

    app.dependency_overrides[get_session] = shared_session_override
    monkeypatch.setattr(
        security_settings,
        "SECRET_KEY",
        "category-integration-test-secret-key-for-hs256",
    )
    token = create_access_token({"sub": str(user.id)})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/categories",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Authenticated aggregate",
                "subcategories": [{"name": "Child", "order": 1}],
            },
        )

        assert response.status_code == 201
        body = response.json()
        headers = {"Authorization": f"Bearer {token}"}
        duplicate = await client.post(
            "/categories",
            headers=headers,
            json={"name": "Authenticated aggregate"},
        )
        assert duplicate.status_code == 409
        assert duplicate.json() == {"detail": "Category already exists"}

        second = await client.post(
            "/categories", headers=headers, json={"name": "Another category"}
        )
        assert second.status_code == 201
        conflicting_update = await client.put(
            f"/categories/{second.json()['id']}",
            headers=headers,
            json={"name": "Authenticated aggregate", "subcategories": []},
        )
        assert conflicting_update.status_code == 409
        missing_delete = await client.delete(f"/categories/{uuid4()}", headers=headers)
        assert missing_delete.status_code == 404
        persisted = await client.get(f"/categories/{body['id']}", headers=headers)
        assert persisted.status_code == 200
        assert len(persisted.json()["subcategories"]) == 1

    assert len(sessions_used) == 6
    assert sessions_used[0].in_transaction() is False
    assert body["name"] == "Authenticated aggregate"
    assert body["subcategories"][0]["name"] == "Child"
    app.dependency_overrides.clear()
