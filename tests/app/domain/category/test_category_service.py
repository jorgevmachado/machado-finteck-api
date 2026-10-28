from contextlib import asynccontextmanager
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import handle_service_exception
from app.domain.category.defaults import load_default_categories
from app.domain.category.repository import CategoryRepository
from app.domain.category.schema import CategoryCreateSchema, CategoryUpdateSchema
from app.domain.category.service import CategoryService
from app.models import Category, Subcategory, utcnow
from app.shared.schemas import FilterPage, Message
from app.temp.service import BaseService


@pytest.fixture
def transaction_state():
    return SimpleNamespace(events=[], commit_error=None)


@pytest.fixture
def repository(transaction_state):
    repository = AsyncMock(spec=CategoryRepository)
    repository.find_by_name.return_value = None
    repository.find_by.return_value = None
    repository.save.side_effect = lambda entity, **kwargs: entity

    @asynccontextmanager
    async def transaction():
        transaction_state.events.append("begin")
        try:
            yield
            transaction_state.events.append("commit")
            if transaction_state.commit_error is not None:
                raise transaction_state.commit_error
        except BaseException:
            transaction_state.events.append("rollback")
            raise

    repository.transaction = Mock(side_effect=transaction)
    return repository


@pytest.fixture
def success_log():
    with patch("app.temp.service.log_service_success") as log:
        yield log


def integrity_error(constraint_name, *, wrapped=False):
    original = RuntimeError("driver error")
    original.diag = SimpleNamespace(constraint_name=constraint_name)
    if wrapped:
        adapter = RuntimeError("adapter error")
        adapter.__cause__ = original
        original = adapter
    return IntegrityError("statement", {}, original)


class TestCategoryService:
    @staticmethod
    def test_from_session_wires_specialized_repository():
        session = AsyncMock()

        service = CategoryService.from_session(session)

        assert isinstance(service.repository, CategoryRepository)
        assert service.repository.session is session

    @staticmethod
    def test_inherits_base_service_and_shares_crud():
        assert issubclass(CategoryService, BaseService)
        for method in ("list_all", "find_by", "create"):
            assert getattr(CategoryService, method) is getattr(BaseService, method)


class TestCategoryServiceList:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("paginated", [False, True])
    async def test_list_preserves_result_and_overrides_owner(
        repository, user, paginated, success_log
    ):
        page_filter = FilterPage.build(
            name="Casa", page=1 if paginated else None, limit=12
        )
        expected = SimpleNamespace(items=[], total=0) if paginated else []
        repository.list_all.return_value = expected

        result = await CategoryService(repository).list_all(page_filter, user)

        assert result is expected
        caller = repository.list_all.await_args.kwargs
        assert caller["user_id"] == user.id
        assert caller["page_filter"] is page_filter
        assert caller["page_filter"].name == "Casa"
        assert caller["page_filter"].page == page_filter.page
        assert caller["page_filter"].limit == 12
        repository.transaction.assert_not_called()
        assert success_log.call_args.kwargs["user_request"] == user.username


class TestCategoryServiceFind:
    @staticmethod
    @pytest.mark.asyncio
    async def test_find_delegates_owner_scoped_aggregate_read(
        repository, user, category_entity, success_log
    ):
        category_entity.is_active = False
        category_entity.subcategories.extend(
            [Subcategory(name="Mercado", order=1, is_active=False)]
        )
        repository.find_by.return_value = category_entity

        result = await CategoryService(repository).find_by(
            user=user, filters={"id": category_entity.id}
        )

        assert result is category_entity
        assert result.subcategories[0].is_active is False
        repository.find_by.assert_awaited_once_with(
            user_id=user.id, filters={"id": category_entity.id}
        )
        repository.transaction.assert_not_called()
        assert success_log.call_args.kwargs["operation"] == "find_by"

    @staticmethod
    @pytest.mark.asyncio
    async def test_missing_or_inaccessible_read_is_not_found(
        repository, user, success_log
    ):
        category_id = uuid4()

        with pytest.raises(HTTPException) as exc:
            await CategoryService(repository).find_by(
                user=user, filters={"id": category_id}
            )

        assert exc.value.status_code == HTTPStatus.NOT_FOUND
        repository.find_by.assert_awaited_once_with(
            user_id=user.id, filters={"id": category_id}
        )
        success_log.assert_not_called()


class TestCategoryServiceFindSubcategory:
    @staticmethod
    @pytest.mark.asyncio
    async def test_returns_owner_scoped_subcategory(
        repository, user, subcategory_entity, success_log
    ):
        repository.find_subcategory_by_id.return_value = subcategory_entity

        result = await CategoryService(repository).find_subcategory_by_id(
            subcategory_id=subcategory_entity.id,
            user_id=user.id,
            user_request=user.username,
        )

        assert result is subcategory_entity
        repository.find_subcategory_by_id.assert_awaited_once_with(
            subcategory_id=subcategory_entity.id, user_id=user.id
        )
        assert success_log.call_args.kwargs["operation"] == "find_subcategory_by_id"
        assert success_log.call_args.kwargs["user_request"] == user.username

    @staticmethod
    @pytest.mark.asyncio
    async def test_missing_or_inaccessible_subcategory_returns_404(
        repository, user, success_log
    ):
        repository.find_subcategory_by_id.return_value = None
        subcategory_id = uuid4()

        with pytest.raises(HTTPException) as caught:
            await CategoryService(repository).find_subcategory_by_id(
                subcategory_id=subcategory_id, user_id=user.id
            )

        assert caught.value.status_code == HTTPStatus.NOT_FOUND
        assert caught.value.detail == "Subcategory not found"
        repository.find_subcategory_by_id.assert_awaited_once_with(
            subcategory_id=subcategory_id, user_id=user.id
        )
        success_log.assert_not_called()

    @staticmethod
    @pytest.mark.asyncio
    async def test_repository_failure_is_handled(repository, user, success_log):
        exception = RuntimeError("database failure")
        repository.find_subcategory_by_id.side_effect = exception

        with (
            patch(
                "app.temp.service.handle_service_exception",
                wraps=handle_service_exception,
            ) as error,
            pytest.raises(HTTPException) as caught,
        ):
            await CategoryService(repository).find_subcategory_by_id(
                subcategory_id=uuid4(), user_id=user.id, user_request=user.username
            )

        assert caught.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        error.assert_called_once()
        assert error.call_args.args[0] is exception
        assert error.call_args.kwargs["operation"] == "find_subcategory_by_id"
        assert error.call_args.kwargs["user_request"] == user.username
        success_log.assert_not_called()


class TestCategoryServiceCreate:
    @staticmethod
    @pytest.mark.asyncio
    async def test_create_builds_owned_aggregate_with_sorted_children_after_commit(
        repository, user, transaction_state, success_log
    ):
        payload = CategoryCreateSchema(
            name="  Casa   principal ",
            is_active=False,
            subcategories=[
                {"name": " Lazer ", "order": 5, "is_active": False},
                {"name": "Mercado", "order": 1, "color": "#aB123F"},
            ],
        )
        success_log.side_effect = lambda *args, **kwargs: (
            transaction_state.events.append("success")
        )

        result = await CategoryService(repository).create(user, payload)

        assert isinstance(result, Category)
        assert result.user_id == user.id
        assert result.name == "Casa principal"
        assert result.is_active is False
        assert result.icon is None and result.color is None
        assert [child.order for child in result.subcategories] == [1, 5]
        first, second = result.subcategories
        assert first.is_active is True and first.color == "#aB123F"
        assert second.is_active is False and second.name == "Lazer"
        assert len({result.id, first.id, second.id}) == 3
        repository.find_by_name.assert_awaited_once_with(
            name="Casa principal", user_id=user.id, exclude_id=None
        )
        repository.save.assert_awaited_once_with(result, user_id=user.id)
        repository.transaction.assert_called_once_with()
        assert transaction_state.events == ["begin", "commit", "success"]

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", ["Casa", "casa", "Água & gás"])
    async def test_create_passes_exact_normalized_name_without_name_code(
        repository, user, name
    ):
        result = await CategoryService(repository).create(
            user, CategoryCreateSchema(name=f" {name} ")
        )

        repository.find_by_name.assert_awaited_once_with(
            name=name, user_id=user.id, exclude_id=None
        )
        assert result.name == name
        assert result.is_active is True
        assert result.subcategories == []

    @staticmethod
    @pytest.mark.asyncio
    async def test_create_rejects_inactive_duplicate_without_saving(
        repository, user, category_entity, transaction_state, success_log
    ):
        category_entity.is_active = False
        repository.find_by_name.return_value = category_entity

        with pytest.raises(HTTPException) as exc:
            await CategoryService(repository).create(
                user, CategoryCreateSchema(name=" Casa ")
            )

        assert exc.value.status_code == HTTPStatus.CONFLICT
        repository.save.assert_not_awaited()
        assert transaction_state.events == ["begin", "rollback"]
        success_log.assert_not_called()


class TestCategoryServiceNormalize:
    @staticmethod
    @pytest.mark.asyncio
    async def test_normalize_skips_duplicate_check_without_name(repository, user):
        service = CategoryService(repository)

        result = await service._normalize({"icon": "house"}, user)

        assert result == {"icon": "house"}
        repository.find_by_name.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_normalize_excludes_self_when_renaming(repository, user):
        service = CategoryService(repository)
        category_id = uuid4()

        await service._normalize({"name": "Casa"}, user, entity_id=category_id)

        repository.find_by_name.assert_awaited_once_with(
            name="Casa", user_id=user.id, exclude_id=category_id
        )


class TestCategoryServiceSeed:
    @staticmethod
    @pytest.mark.asyncio
    async def test_seeds_entire_catalog_with_one_commit_and_preserves_existing(
        repository, user, category_entity, transaction_state, success_log
    ):
        category_entity.is_active = False
        repository.find_by_name.side_effect = [category_entity] + [None] * 13
        success_log.side_effect = lambda *args, **kwargs: (
            transaction_state.events.append("success")
        )

        result = await CategoryService(repository).seed_defaults(user)

        assert result.model_dump() == {"created": 13, "skipped": 1}
        repository.transaction.assert_called_once_with()
        assert transaction_state.events == ["begin", "commit", "success"]
        payloads = load_default_categories()
        assert [call.kwargs for call in repository.find_by_name.await_args_list] == [
            {"name": payload.name, "user_id": user.id} for payload in payloads
        ]
        entities = [call.kwargs["entity"] for call in repository.save.await_args_list]
        assert len(entities) == 13
        for entity, payload in zip(entities, payloads[1:], strict=True):
            assert entity.user_id == user.id
            assert entity.name == payload.name
            assert entity.icon == payload.icon and entity.color == payload.color
            assert entity.is_active is True
            assert [
                (child.name, child.icon, child.color, child.order)
                for child in entity.subcategories
            ] == [
                (child.name, child.icon, child.color, child.order)
                for child in payload.subcategories
            ]
        assert category_entity.is_active is False
        assert category_entity.name == "Casa"
        repository.delete.assert_not_awaited()
        assert success_log.call_args.kwargs["user_request"] == user.username

    @staticmethod
    @pytest.mark.asyncio
    async def test_repeated_seed_skips_every_existing_aggregate(
        repository, user, category_entity, success_log
    ):
        repository.find_by_name.return_value = category_entity

        result = await CategoryService(repository).seed_defaults(user)

        assert result.model_dump() == {"created": 0, "skipped": 14}
        repository.save.assert_not_awaited()
        assert success_log.call_args.kwargs["operation"] == "seed_defaults"

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("phase", ["flush", "commit"])
    @pytest.mark.parametrize("name_conflict", [False, True])
    async def test_seed_failures_roll_back_without_logging_success(
        repository, user, transaction_state, success_log, phase, name_conflict
    ):
        failure = (
            integrity_error("uq_categories_owner_name_live")
            if name_conflict
            else RuntimeError("Database unavailable")
        )
        if phase == "flush":
            repository.save.side_effect = [
                Category(user_id=user.id, name="One"),
                failure,
            ]
        else:
            transaction_state.commit_error = failure

        with pytest.raises(HTTPException) as exc:
            await CategoryService(repository).seed_defaults(user)

        assert exc.value.status_code == (
            HTTPStatus.CONFLICT if name_conflict else HTTPStatus.INTERNAL_SERVER_ERROR
        )
        assert transaction_state.events[-1] == "rollback"
        success_log.assert_not_called()


class TestCategoryServiceUpdate:
    @staticmethod
    @pytest.mark.asyncio
    async def test_rename_without_list_preserves_children_and_skips_plan(
        repository, user, category_entity, transaction_state, monkeypatch
    ):
        child = Subcategory(
            name="Mercado", order=5, icon="basket", color="#123456", is_active=False
        )
        category_entity.subcategories.append(child)
        repository.find_by.return_value = category_entity
        before = (
            child.id,
            child.name,
            child.order,
            child.icon,
            child.color,
            child.is_active,
            child.created_at,
            child.updated_at,
            child.deleted_at,
        )

        def unexpected_reconciliation(*args, **kwargs):
            pytest.fail("An omitted child list must not be reconciled")

        monkeypatch.setattr(
            "app.domain.category.service.build_subcategory_reconciliation_plan",
            unexpected_reconciliation,
        )
        await CategoryService(repository).update(
            category_entity.id, CategoryUpdateSchema(name="Novo nome"), user
        )

        assert category_entity.name == "Novo nome"
        assert category_entity.subcategories == [child]
        assert (
            child.id,
            child.name,
            child.order,
            child.icon,
            child.color,
            child.is_active,
            child.created_at,
            child.updated_at,
            child.deleted_at,
        ) == before
        repository.save.assert_awaited_once_with(
            entity=category_entity, user_id=user.id, reconciliation=None
        )
        assert transaction_state.events == ["begin", "commit"]

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_locks_and_delegates_mixed_reconciliation_plan(
        repository, user, category_entity, transaction_state, success_log
    ):
        retained = Subcategory(name="Mercado", order=1, icon="old", is_active=False)
        removed = Subcategory(name="Restaurantes", order=5)
        historical = Subcategory(name="Historico", order=9)
        historical.deleted_at = utcnow()
        category_entity.subcategories.extend([retained, removed, historical])
        repository.find_by.return_value = category_entity
        payload = CategoryUpdateSchema(
            name=" Casa   nova ",
            subcategories=[
                {"id": retained.id, "name": "Mercado novo", "order": 5},
                {"name": "Novo", "order": 1},
            ],
        )
        success_log.side_effect = lambda *args, **kwargs: (
            transaction_state.events.append("success")
        )

        result = await CategoryService(repository).update(
            category_entity.id, payload, user
        )

        assert isinstance(result, Message)
        assert category_entity.name == "Casa nova"
        repository.find_by.assert_awaited_once_with(
            id=category_entity.id, user_id=user.id, for_update=True
        )
        repository.find_by_name.assert_awaited_once_with(
            name="Casa nova", user_id=user.id, exclude_id=category_entity.id
        )
        repository.save.assert_awaited_once()
        arguments = repository.save.await_args.kwargs
        assert arguments["entity"] is category_entity
        assert arguments["user_id"] == user.id
        plan = arguments["reconciliation"]
        assert plan.remove_ids == (removed.id,)
        assert plan.updates[0].id == retained.id
        assert plan.updates[0].name == "Mercado novo"
        assert plan.updates[0].icon is None
        assert plan.updates[0].color is None
        assert plan.updates[0].is_active is True
        assert plan.updates[0].order == 5
        assert plan.creates[0].name == "Novo"
        assert plan.creates[0].order == 1
        repository.update.assert_not_awaited()
        repository.transaction.assert_called_once_with()
        assert transaction_state.events == ["begin", "commit", "success"]

    @staticmethod
    @pytest.mark.asyncio
    async def test_omitted_root_fields_preserved_explicit_null_clears_icon(
        repository, user, category_entity
    ):
        category_entity.icon = "house"
        category_entity.color = "#123456"
        category_entity.is_active = False
        child = Subcategory(name="Mercado", order=1)
        category_entity.subcategories.append(child)
        repository.find_by.return_value = category_entity

        await CategoryService(repository).update(
            category_entity.id,
            CategoryUpdateSchema(icon=None, subcategories=[]),
            user,
        )

        assert category_entity.icon is None
        assert category_entity.color == "#123456"
        assert category_entity.name == "Casa"
        assert category_entity.is_active is False
        plan = repository.save.await_args.kwargs["reconciliation"]
        assert plan.remove_ids == (child.id,)
        assert plan.creates == () and plan.updates == ()
        repository.find_by_name.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_same_name_excludes_self_and_allows_other_root_updates(
        repository, user, category_entity
    ):
        repository.find_by.return_value = category_entity

        await CategoryService(repository).update(
            category_entity.id,
            CategoryUpdateSchema(
                name=" Casa ", color=None, is_active=False, subcategories=[]
            ),
            user,
        )

        repository.find_by_name.assert_awaited_once_with(
            name="Casa", user_id=user.id, exclude_id=category_entity.id
        )
        assert category_entity.color is None
        assert category_entity.is_active is False
        repository.save.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_duplicate_rename_does_not_mutate_aggregate(
        repository, user, category_entity, transaction_state, success_log
    ):
        repository.find_by.return_value = category_entity
        repository.find_by_name.return_value = Category(
            user_id=user.id, name="Lazer", is_active=False
        )

        with pytest.raises(HTTPException) as exc:
            await CategoryService(repository).update(
                category_entity.id,
                CategoryUpdateSchema(name="Lazer", subcategories=[]),
                user,
            )

        assert exc.value.status_code == HTTPStatus.CONFLICT
        assert category_entity.name == "Casa"
        repository.save.assert_not_awaited()
        assert transaction_state.events == ["begin", "rollback"]
        success_log.assert_not_called()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "invalid_children",
        [
            [{"name": "A", "order": 1}, {"name": "B", "order": 1}],
            [{"id": uuid4(), "name": "Estranho", "order": 1}],
            "duplicate-id",
            "deleted-id",
        ],
    )
    async def test_invalid_plan_rejected_before_mutating_root_or_children(
        repository,
        user,
        category_entity,
        invalid_children,
        transaction_state,
        success_log,
    ):
        child = Subcategory(name="Original", order=1, is_active=False)
        category_entity.subcategories.append(child)
        if invalid_children == "duplicate-id":
            invalid_children = [
                {"id": child.id, "name": "A", "order": 1},
                {"id": child.id, "name": "B", "order": 2},
            ]
        elif invalid_children == "deleted-id":
            child.deleted_at = utcnow()
            invalid_children = [{"id": child.id, "name": "Restaurado", "order": 1}]
        repository.find_by.return_value = category_entity

        with pytest.raises(HTTPException) as exc:
            await CategoryService(repository).update(
                category_entity.id,
                CategoryUpdateSchema(
                    name="Nao deve mudar", subcategories=invalid_children
                ),
                user,
            )

        assert exc.value.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
        assert category_entity.name == "Casa"
        assert child.name == "Original"
        repository.save.assert_not_awaited()
        repository.find_by_name.assert_not_awaited()
        assert transaction_state.events == ["begin", "rollback"]
        success_log.assert_not_called()


class TestCategoryServiceDelete:
    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_delegates_complete_aggregate_inside_transaction(
        repository, user, category_entity, transaction_state, success_log
    ):
        repository.find_by.return_value = category_entity
        success_log.side_effect = lambda *args, **kwargs: (
            transaction_state.events.append("success")
        )

        result = await CategoryService(repository).delete(user, category_entity.id)

        assert isinstance(result, Message)
        repository.find_by.assert_awaited_once_with(
            id=category_entity.id, user_id=user.id, for_update=True
        )
        repository.delete.assert_awaited_once_with(category_entity, user_id=user.id)
        repository.save.assert_not_awaited()
        repository.transaction.assert_called_once_with()
        assert transaction_state.events == ["begin", "commit", "success"]


class TestCategoryServiceErrors:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("operation", ["update", "delete"])
    async def test_missing_foreign_or_deleted_target_is_not_upserted(
        repository, user, operation, transaction_state, success_log
    ):
        category_id = uuid4()
        service = CategoryService(repository)

        with pytest.raises(HTTPException) as exc:
            if operation == "update":
                await service.update(
                    category_id, CategoryUpdateSchema(subcategories=[]), user
                )
            else:
                await service.delete(user, category_id)

        assert exc.value.status_code == HTTPStatus.NOT_FOUND
        repository.find_by.assert_awaited_once_with(
            id=category_id, user_id=user.id, for_update=True
        )
        repository.save.assert_not_awaited()
        repository.delete.assert_not_awaited()
        assert transaction_state.events == ["begin", "rollback"]
        success_log.assert_not_called()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("phase", ["flush", "commit"])
    @pytest.mark.parametrize("wrapped", [False, True])
    @pytest.mark.parametrize(
        "constraint,status",
        [
            ("uq_categories_owner_name_live", HTTPStatus.CONFLICT),
            ("uq_subcategories_category_live_order", HTTPStatus.UNPROCESSABLE_CONTENT),
            ("fk_categories_user_id_users", HTTPStatus.INTERNAL_SERVER_ERROR),
        ],
    )
    async def test_integrity_diagnostic_mapped_only_after_rollback(
        repository,
        user,
        category_entity,
        transaction_state,
        success_log,
        phase,
        wrapped,
        constraint,
        status,
    ):
        repository.find_by.return_value = category_entity
        failure = integrity_error(constraint, wrapped=wrapped)
        if phase == "flush":
            repository.save.side_effect = failure
        else:
            transaction_state.commit_error = failure

        error = handle_service_exception

        with patch(
            "app.temp.service.handle_service_exception",
            wraps=error,
        ) as handler:
            with pytest.raises(HTTPException) as exc:
                await CategoryService(repository).update(
                    category_entity.id,
                    CategoryUpdateSchema(subcategories=[]),
                    user,
                )

        assert exc.value.status_code == status
        handler.assert_called_once()
        assert handler.call_args.kwargs["operation"] == "update"
        assert handler.call_args.kwargs["user_request"] == user.username
        repository.save.assert_awaited_once()
        success_log.assert_not_called()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("operation", ["create", "delete"])
    async def test_commit_failure_cannot_report_success(
        repository, user, category_entity, transaction_state, success_log, operation
    ):
        repository.find_by.return_value = category_entity
        transaction_state.commit_error = integrity_error(
            "uq_categories_owner_name_live"
        )
        service = CategoryService(repository)

        with pytest.raises(HTTPException) as exc:
            if operation == "create":
                await service.create(user, CategoryCreateSchema(name="Nova"))
            else:
                await service.delete(user, category_entity.id)

        assert exc.value.status_code == HTTPStatus.CONFLICT
        assert transaction_state.events == ["begin", "commit", "rollback"]
        success_log.assert_not_called()

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "operation", ["create", "list_all", "find_by", "update", "delete"]
    )
    @pytest.mark.parametrize("failure_type", [RuntimeError, ValueError])
    async def test_infrastructure_errors_use_standard_explicit_handler(
        repository, user, category_entity, success_log, operation, failure_type
    ):
        service = CategoryService(repository)
        failure = failure_type("database unavailable")
        repository.find_by.return_value = category_entity
        if operation == "create":
            repository.save.side_effect = failure
            call = service.create(user, CategoryCreateSchema(name="Casa"))
        elif operation == "list_all":
            repository.list_all.side_effect = failure
            call = service.list_all(FilterPage(), user)
        elif operation == "find_by":
            repository.find_by.side_effect = failure
            call = service.find_by(user=user, filters={"id": category_entity.id})
        elif operation == "update":
            repository.save.side_effect = failure
            call = service.update(
                category_entity.id, CategoryUpdateSchema(subcategories=[]), user
            )
        else:
            repository.delete.side_effect = failure
            call = service.delete(user, category_entity.id)

        with patch(
            "app.temp.service.handle_service_exception",
            wraps=handle_service_exception,
        ) as handler:
            with pytest.raises(HTTPException) as exc:
                await call

        assert exc.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert exc.value.detail == "Internal server error"
        assert handler.call_args.args[0] is failure
        assert handler.call_args.kwargs["operation"] == operation
        assert handler.call_args.kwargs["raise_exception"] is True
        success_log.assert_not_called()

    @staticmethod
    @pytest.mark.asyncio
    async def test_constraint_name_in_message_alone_is_not_translated(
        repository, user, success_log
    ):
        repository.save.side_effect = IntegrityError(
            "statement", {}, RuntimeError("uq_categories_owner_name_live")
        )

        with pytest.raises(HTTPException) as exc:
            await CategoryService(repository).create(
                user, CategoryCreateSchema(name="Casa")
            )

        assert exc.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        success_log.assert_not_called()
