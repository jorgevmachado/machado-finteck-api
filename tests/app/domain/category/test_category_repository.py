from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from sqlalchemy.dialects import postgresql

import pytest

from app.core.pagination.schemas import CustomLimitOffsetPage
from app.domain.category.repository import CategoryRepository
from app.models import Subcategory
from app.shared.schemas import FilterPage


def repository_session(*, active_transaction: bool = False):
    return SimpleNamespace(
        info={},
        in_transaction=Mock(return_value=active_transaction),
        in_nested_transaction=Mock(return_value=False),
        begin=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
        add=Mock(),
        flush=AsyncMock(),
        scalar=AsyncMock(),
        scalars=AsyncMock(),
    )


def owned_transaction_session():
    session = repository_session()
    session.info["app.temp.transaction_active"] = True
    return session


class TestCategoryRepositoryTransaction:
    @staticmethod
    @pytest.mark.asyncio
    async def test_adopts_autobegun_session_and_commits_aggregate(
        category_entity, subcategory_entity
    ):
        session = repository_session(active_transaction=True)
        repository = CategoryRepository(session)
        category_entity.subcategories.append(subcategory_entity)

        async with repository.transaction():
            result = await repository.save(category_entity)

        assert result is category_entity
        session.begin.assert_not_awaited()
        session.add.assert_called_once_with(category_entity)
        session.flush.assert_awaited_once()
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_starts_transaction_when_session_has_not_autobegun():
        session = repository_session()
        repository = CategoryRepository(session)

        async with repository.transaction():
            pass

        session.begin.assert_awaited_once()
        session.commit.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_rolls_back_flush_failure(category_entity):
        session = repository_session()
        session.flush.side_effect = RuntimeError("flush failed")
        repository = CategoryRepository(session)

        with pytest.raises(RuntimeError, match="flush failed"):
            async with repository.transaction():
                await repository.save(category_entity)

        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_rolls_back_commit_failure():
        session = repository_session()
        session.commit.side_effect = RuntimeError("commit failed")
        repository = CategoryRepository(session)

        with pytest.raises(RuntimeError, match="commit failed"):
            async with repository.transaction():
                pass

        session.rollback.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_rejects_nested_transaction_context():
        session = repository_session()
        repository = CategoryRepository(session)

        with pytest.raises(RuntimeError, match="Nested"):
            async with repository.transaction():
                async with repository.transaction():
                    pass

        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_rejects_existing_session_savepoint():
        session = repository_session()
        session.in_nested_transaction.return_value = True

        with pytest.raises(RuntimeError, match="Nested"):
            async with CategoryRepository(session).transaction():
                pytest.fail("A savepoint cannot own the aggregate transaction")

        session.begin.assert_not_awaited()
        session.commit.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_rollback_failure_is_logged_without_hiding_original_error(caplog):
        session = repository_session()
        session.commit.side_effect = RuntimeError("commit failed")
        session.rollback.side_effect = RuntimeError("connection lost")

        with pytest.raises(RuntimeError, match="commit failed"):
            async with CategoryRepository(session).transaction():
                pass

        assert "Failed to roll back experimental transaction" in caplog.text
        assert "connection lost" in caplog.text
        assert session.info == {}

    @staticmethod
    @pytest.mark.asyncio
    async def test_save_and_delete_require_transaction(category_entity):
        repository = CategoryRepository(repository_session(active_transaction=True))

        with pytest.raises(RuntimeError, match="inside transaction"):
            await repository.save(category_entity)
        with pytest.raises(RuntimeError, match="inside transaction"):
            await repository.delete(category_entity)
        with pytest.raises(RuntimeError, match="inside transaction"):
            await repository.update(category_entity)

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_alias_flushes_without_intermediate_commit(category_entity):
        session = repository_session(active_transaction=True)
        repository = CategoryRepository(session)

        async with repository.transaction():
            assert await repository.update(category_entity) is category_entity

        session.flush.assert_awaited_once()
        session.commit.assert_awaited_once()


class TestCategoryRepositoryQueries:
    @staticmethod
    @pytest.mark.asyncio
    async def test_find_subcategory_scopes_owner_and_excludes_deleted_entities(
        subcategory_entity,
    ):
        session = repository_session()
        session.scalar.return_value = subcategory_entity
        user_id = uuid4()

        result = await CategoryRepository(session).find_subcategory_by_id(
            subcategory_id=subcategory_entity.id, user_id=user_id
        )

        assert result is subcategory_entity
        query = session.scalar.await_args.args[0]
        compiled = query.compile(dialect=postgresql.dialect())
        sql = str(compiled)
        assert "JOIN categories ON categories.id = subcategories.category_id" in sql
        assert "subcategories.id =" in sql
        assert "categories.user_id =" in sql
        assert "subcategories.deleted_at IS NULL" in sql
        assert "categories.deleted_at IS NULL" in sql
        assert subcategory_entity.id in compiled.params.values()
        assert user_id in compiled.params.values()

    @staticmethod
    @pytest.mark.asyncio
    async def test_missing_locked_root_does_not_reload_children():
        session = repository_session()
        session.scalar.return_value = None

        result = await CategoryRepository(session).find_by(
            id=uuid4(), user_id=uuid4(), for_update=True
        )

        assert result is None
        session.scalar.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_scopes_to_owner_and_hides_deleted_categories():
        session = repository_session()
        repository = CategoryRepository(session)
        category_id = uuid4()
        user_id = uuid4()

        await repository.find_by(id=category_id, user_id=user_id)

        sql = str(
            session.scalar.await_args.args[0].compile(dialect=postgresql.dialect())
        )
        assert "categories.id =" in sql
        assert "categories.user_id =" in sql
        assert "categories.deleted_at IS NULL" in sql

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_for_update_locks_root_then_reloads_children():
        session = repository_session(active_transaction=True)
        session.scalar.side_effect = [category_entity := object(), category_entity]
        repository = CategoryRepository(session)

        assert (
            await repository.find_by(id=uuid4(), user_id=uuid4(), for_update=True)
            is category_entity
        )

        lock_sql = str(
            session.scalar.await_args_list[0]
            .args[0]
            .compile(dialect=postgresql.dialect())
        )
        reload_statement = session.scalar.await_args_list[1].args[0]
        assert "FOR UPDATE OF categories" in lock_sql
        assert reload_statement.get_execution_options()["populate_existing"] is True
        assert session.scalar.await_count == 2

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_name_excludes_requested_category():
        session = repository_session()
        repository = CategoryRepository(session)
        category_id = uuid4()
        user_id = uuid4()

        await repository.find_by_name(
            name="Casa", user_id=user_id, exclude_id=category_id
        )

        sql = str(
            session.scalar.await_args.args[0].compile(dialect=postgresql.dialect())
        )
        assert "categories.name =" in sql
        assert "categories.user_id =" in sql
        assert "categories.deleted_at IS NULL" in sql
        assert "categories.id !=" in sql

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_counts_root_categories_and_applies_owner_filter():
        session = repository_session()
        session.scalars.return_value = SimpleNamespace(all=Mock(return_value=[]))
        session.scalar.return_value = 0
        repository = CategoryRepository(session)
        owner_id = uuid4()
        page_filter = FilterPage.build(name="Casa", page=1, limit=5)

        result = await repository.list_all(user_id=owner_id, page_filter=page_filter)

        assert isinstance(result, CustomLimitOffsetPage)
        assert result.meta.total == 0
        count_sql = str(
            session.scalar.await_args.args[0].compile(dialect=postgresql.dialect())
        )
        page_sql = str(
            session.scalars.await_args.args[0].compile(dialect=postgresql.dialect())
        )
        assert "categories.user_id =" in count_sql
        assert "categories.deleted_at IS NULL" in count_sql
        assert "categories.name =" in count_sql
        assert "LIMIT" in page_sql

    @staticmethod
    @pytest.mark.asyncio
    async def test_unpaginated_listing_returns_list():
        session = repository_session()
        expected = [object()]
        session.scalars.return_value = SimpleNamespace(all=Mock(return_value=expected))
        repository = CategoryRepository(session)
        page_filter = FilterPage.build(limit=12)

        result = await repository.list_all(user_id=uuid4(), page_filter=page_filter)

        assert result == expected
        session.scalar.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("page_filter", [None, FilterPage()])
    async def test_listing_without_owner_fails_closed(page_filter):
        repository = CategoryRepository(repository_session())

        with pytest.raises(ValueError, match="trusted owner"):
            await repository.list_all(user_id=None, page_filter=page_filter)

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_rejects_missing_id():
        repository = CategoryRepository(repository_session())
        with pytest.raises(ValueError, match="find_by requires id or filters"):
            await repository.find_by(user_id=uuid4())

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_rejects_criteria_beyond_id():
        repository = CategoryRepository(repository_session())
        with pytest.raises(ValueError, match="only the id criterion"):
            await repository.find_by(
                user_id=uuid4(), filters={"id": uuid4(), "name": "Casa"}
            )


class TestCategoryRepositoryOwnedWrites:
    @staticmethod
    @pytest.mark.asyncio
    async def test_save_enforces_trusted_owner(category_entity):
        repository = CategoryRepository(owned_transaction_session())
        with pytest.raises(ValueError, match="trusted owner"):
            await repository.save(category_entity, user_id=uuid4())

    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_enforces_trusted_owner(category_entity):
        repository = CategoryRepository(owned_transaction_session())
        with pytest.raises(ValueError, match="trusted owner"):
            await repository.delete(category_entity, user_id=uuid4())

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_forwards_owner_to_save(category_entity):
        repository = CategoryRepository(owned_transaction_session())
        with pytest.raises(ValueError, match="trusted owner"):
            await repository.update(category_entity, user_id=uuid4())

    @staticmethod
    @pytest.mark.asyncio
    async def test_visibility_filters_hides_deleted_roots():
        repository = CategoryRepository(repository_session())
        predicates = repository._visibility()
        assert len(predicates) == 1
        sql = str(predicates[0].compile(dialect=postgresql.dialect()))
        assert "deleted_at IS NULL" in sql


class TestCategoryRepositoryWrites:
    @staticmethod
    @pytest.mark.asyncio
    async def test_saving_persisted_root_updates_timestamp(
        category_entity, monkeypatch
    ):
        session = repository_session()
        repository = CategoryRepository(session)
        monkeypatch.setattr(
            repository, "_state", lambda entity: SimpleNamespace(persistent=True)
        )

        async with repository.transaction():
            await repository.save(category_entity)

        assert category_entity.updated_at is not None
        session.flush.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_save_applies_reconciliation_without_committing(
        category_entity, category_reconciliation_payload
    ):
        from app.domain.category.business import (
            build_subcategory_reconciliation_plan,
        )

        category_entity.subcategories.extend(
            [
                Subcategory(name="Mercado", order=1),
                Subcategory(name="Bares", order=3),
            ]
        )
        existing_ids = [child.id for child in category_entity.subcategories]
        payload = [
            category_reconciliation_payload[0].model_copy(
                update={"id": existing_ids[0]}
            ),
            category_reconciliation_payload[1],
        ]
        plan = build_subcategory_reconciliation_plan(payload, existing_ids)
        session = repository_session(active_transaction=True)
        repository = CategoryRepository(session)

        async with repository.transaction():
            await repository.save(category_entity, reconciliation=plan)

        assert category_entity.subcategories[0].name == "Mercado atualizado"
        assert category_entity.subcategories[0].order == 2
        assert category_entity.subcategories[1].deleted_at is not None
        assert category_entity.subcategories[1].is_active is False
        assert len(category_entity.subcategories) == 3
        session.commit.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_is_logical_and_preserves_prior_child_timestamp(
        category_entity, subcategory_entity
    ):
        old_timestamp = subcategory_entity.created_at
        deleted_child = Subcategory(name="Historical", order=2)
        deleted_child.deleted_at = old_timestamp
        category_entity.subcategories.extend([subcategory_entity, deleted_child])
        repository = CategoryRepository(repository_session(active_transaction=True))

        async with repository.transaction():
            await repository.delete(category_entity)

        assert category_entity.deleted_at is not None
        assert category_entity.is_active is False
        assert subcategory_entity.deleted_at == category_entity.deleted_at
        assert subcategory_entity.is_active is False
        assert deleted_child.deleted_at == old_timestamp
