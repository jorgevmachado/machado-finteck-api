import types
from uuid import uuid4
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi_pagination import LimitOffsetPage, LimitOffsetParams
from sqlalchemy import ForeignKey, String, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from app.core.database.base import table_registry
from app.core.pagination.schemas import CustomLimitOffsetPage
from app.core.repository import BaseRepository
from app.models.auth.role import Role
from app.models.auth.user import User
from app.shared.schemas import FilterPage


@table_registry.mapped_as_dataclass
class UserProfileTest:
    __tablename__ = "user_profiles_test"

    account_id: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

    user: Mapped[User] = relationship("User", init=False)
    id: Mapped[str] = mapped_column(
        String, primary_key=True, default_factory=lambda: str(uuid4()), init=False
    )


class UserBaseRepository(BaseRepository[User]):
    model = User
    relations = (selectinload(User.role),)
    default_order_by = "name"


class UserProfileBaseRepository(BaseRepository[UserProfileTest]):
    model = UserProfileTest


class RoleBaseRepository(BaseRepository[Role]):
    model = Role


class TestBaseRepositoryApplyOrderBy:
    @staticmethod
    def test_apply_order_by_returns_same_query_when_order_by_is_none():
        repository = UserProfileBaseRepository(session=AsyncMock())
        query = select(UserProfileTest)
        page_filter = FilterPage()

        result_query = repository._apply_order_by(query, page_filter)

        assert result_query is query
        assert "ORDER BY" not in str(result_query)

    @staticmethod
    def test_apply_order_by_returns_same_query_when_order_path_is_blank():
        repository = UserBaseRepository(session=AsyncMock())
        query = select(User)
        page_filter = FilterPage.build(order_by="   ")

        result_query = repository._apply_order_by(query, page_filter)

        assert result_query is query
        assert "ORDER BY" not in str(result_query)

    @staticmethod
    def test_apply_order_by_uses_default_order_by_when_page_filter_is_none():
        repository = UserBaseRepository(session=AsyncMock())
        query = select(User)

        result_query = repository._apply_order_by(query)

        assert "ORDER BY users.name" in str(result_query)

    @staticmethod
    def test_apply_order_by_uses_page_filter_order_by_when_provided():
        repository = UserBaseRepository(session=AsyncMock())
        query = select(User)
        page_filter = FilterPage.build(order_by="name")

        result_query = repository._apply_order_by(query, page_filter)

        assert "ORDER BY users.name" in str(result_query)

    @staticmethod
    def test_apply_order_by_applies_outer_join_for_relationship_path():
        repository = UserProfileBaseRepository(session=AsyncMock())
        query = select(UserProfileTest)
        page_filter = FilterPage.build(order_by="user.role.name")

        result_query = repository._apply_order_by(query, page_filter)
        result_query_str = str(result_query)

        assert "LEFT OUTER JOIN users" in result_query_str
        assert "LEFT OUTER JOIN roles" in result_query_str
        assert "ORDER BY roles.name" in result_query_str

    @staticmethod
    def test_apply_order_by_raises_error_when_relation_is_invalid():
        repository = UserProfileBaseRepository(session=AsyncMock())
        query = select(UserProfileTest)
        page_filter = FilterPage.build(order_by="invalid.role")

        with pytest.raises(ValueError, match="Invalid default_order_by relation"):
            repository._apply_order_by(query, page_filter)

    @staticmethod
    def test_apply_order_by_raises_error_for_collection_relationship():
        repository = UserBaseRepository(session=AsyncMock())
        query = select(User)
        page_filter = FilterPage.build(order_by="role.users.name")

        with pytest.raises(
            ValueError, match="collection relationships are not supported"
        ):
            repository._apply_order_by(query, page_filter)

    @staticmethod
    def test_apply_order_by_raises_error_when_path_token_is_not_relationship():
        repository = UserBaseRepository(session=AsyncMock())
        query = select(User)
        page_filter = FilterPage.build(order_by="name.id")

        with pytest.raises(ValueError, match="is not a relationship"):
            repository._apply_order_by(query, page_filter)

    @staticmethod
    def test_apply_order_by_raises_error_when_last_field_is_invalid():
        repository = UserProfileBaseRepository(session=AsyncMock())
        query = select(UserProfileTest)
        page_filter = FilterPage.build(order_by="user.invalid_field")

        with pytest.raises(ValueError, match="Invalid default_order_by field"):
            repository._apply_order_by(query, page_filter)

    @staticmethod
    def test_apply_order_by_raises_error_when_last_token_is_not_column():
        repository = UserProfileBaseRepository(session=AsyncMock())
        query = select(UserProfileTest)
        page_filter = FilterPage.build(order_by="user.role")

        with pytest.raises(ValueError, match="last token must be a mapped column"):
            repository._apply_order_by(query, page_filter)


class TestBaseRepositoryRelationHelpers:
    @staticmethod
    def test_extract_relations_filters_extracts_and_mutates_raw_filters():
        raw_filters = {
            "user_name": "alice",
            "status": "active",
            "user_": "ignored",
            "account_id": "account-id",
            "user_order": None,
        }

        result = BaseRepository._extract_relations_filters(raw_filters, relation="user")

        assert result == {
            "name": "alice",
        }
        assert "user_name" not in raw_filters
        assert raw_filters["status"] == "active"
        assert "account_id" in raw_filters
        assert "user_" in raw_filters

    @staticmethod
    def test_build_name_predicate_returns_none_when_attr_has_no_mapper():
        predicate = BaseRepository._build_name_predicate(
            User.name,
            User.name.property,
            "alice",
        )

        assert predicate is None

    @staticmethod
    def test_build_name_predicate_builds_any_for_uselist_relationship():
        predicate = BaseRepository._build_name_predicate(
            Role.users,
            Role.users.property,
            "alice",
        )

        predicate_sql = str(predicate)
        assert predicate is not None
        assert ".name" in predicate_sql

    @staticmethod
    def test_build_name_predicate_builds_has_for_scalar_relationship():
        predicate = BaseRepository._build_name_predicate(
            UserProfileTest.user,
            UserProfileTest.user.property,
            "alice",
        )

        predicate_sql = str(predicate)
        assert predicate is not None
        assert "users.name" in predicate_sql

    @staticmethod
    def test_build_name_predicate_returns_none_when_related_model_has_no_name_attr():
        related_model = types.SimpleNamespace()
        model_property = types.SimpleNamespace(
            mapper=types.SimpleNamespace(class_=related_model),
            uselist=False,
        )

        predicate = BaseRepository._build_name_predicate(
            model_attr=Mock(),
            model_property=model_property,
            value="alice",
        )

        assert predicate is None

    @staticmethod
    def test_build_single_token_predicate_delegates_to_build_name_predicate():
        repository = UserBaseRepository(session=AsyncMock())

        with patch.object(
            repository,
            "_build_name_predicate",
            return_value="delegated-predicate",
        ) as build_name_predicate_mock:
            result = repository._build_single_token_predicate(
                Role.users,
                Role.users.property,
                "alice",
            )

        assert result == "delegated-predicate"
        build_name_predicate_mock.assert_called_once_with(
            Role.users,
            Role.users.property,
            "alice",
        )

    @staticmethod
    def test_build_nested_predicate_returns_none_when_property_is_not_relationship():
        repository = UserBaseRepository(session=AsyncMock())

        predicate = repository._build_nested_predicate(
            User.name,
            User.name.property,
            ["name", "id"],
            "alice",
        )

        assert predicate is None

    @staticmethod
    def test_build_nested_predicate_builds_predicate_for_relationship_path():
        repository = UserBaseRepository(session=AsyncMock())

        predicate = repository._build_nested_predicate(
            Role.users,
            Role.users.property,
            ["users", "name"],
            "alice",
        )

        predicate_sql = str(predicate)
        assert predicate is not None
        assert ".name" in predicate_sql

    @staticmethod
    def test_build_nested_predicate_returns_none_when_nested_predicate_is_none():
        repository = UserProfileBaseRepository(session=AsyncMock())

        with patch.object(repository, "_build_relation_predicate", return_value=None):
            predicate = repository._build_nested_predicate(
                UserProfileTest.user,
                UserProfileTest.user.property,
                ["user", "name"],
                "alice",
            )

        assert predicate is None

    @staticmethod
    def test_build_nested_predicate_builds_has_for_scalar_relationship():
        repository = UserProfileBaseRepository(session=AsyncMock())
        nested_predicate = User.name == "alice"

        with patch.object(
            repository,
            "_build_relation_predicate",
            return_value=nested_predicate,
        ):
            predicate = repository._build_nested_predicate(
                UserProfileTest.user,
                UserProfileTest.user.property,
                ["user", "name"],
                "alice",
            )

        assert predicate is not None
        assert "users.name" in str(predicate)

    @staticmethod
    def test_build_relation_predicate_handles_empty_path():
        repository = UserBaseRepository(session=AsyncMock())

        predicate = repository._build_relation_predicate(User, [], "admin")

        assert predicate is None

    @staticmethod
    def test_resolve_relation_name_returns_none_when_model_has_no_mapper():
        repository = UserBaseRepository(session=AsyncMock())
        repository.model = object

        result = repository._resolve_relation_name({"user_name": "alice"})

        assert result is None

    @staticmethod
    def test_build_relation_predicate_returns_none_for_invalid_attr():
        repository = UserBaseRepository(session=AsyncMock())

        predicate = repository._build_relation_predicate(User, ["not_exists"], "admin")

        assert predicate is None

    @staticmethod
    def test_build_relation_predicate_builds_column_predicate_for_single_token():
        repository = UserBaseRepository(session=AsyncMock())

        predicate = repository._build_relation_predicate(User, ["name"], "alice")

        assert predicate is not None
        assert "users.name" in str(predicate)

    @staticmethod
    def test_build_relation_predicate_builds_nested_relationship_predicate():
        repository = UserBaseRepository(session=AsyncMock())

        predicate = repository._build_relation_predicate(
            User, ["role", "name"], "admin"
        )

        assert predicate is not None
        assert "roles.name" in str(predicate)

    @staticmethod
    def test_apply_relations_filters_returns_query_when_relation_attr_not_found():
        repository = UserProfileBaseRepository(session=AsyncMock())
        query = select(UserProfileTest)

        result_query = repository._apply_relations_filters(
            query,
            relations_filters={"name": "alice"},
            relation="not_exists",
        )

        assert result_query is query

    @staticmethod
    def test_apply_relations_filters_returns_query_when_relation_has_no_mapper():
        repository = UserProfileBaseRepository(session=AsyncMock())
        query = select(UserProfileTest)

        result_query = repository._apply_relations_filters(
            query,
            relations_filters={"name": "alice"},
            relation="nickname",
        )

        assert result_query is query

    @staticmethod
    def test_apply_relations_filters_returns_same_query_for_empty_filters():
        repository = UserProfileBaseRepository(session=AsyncMock())
        query = select(UserProfileTest)

        result_query = repository._apply_relations_filters(
            query,
            relations_filters={},
            relation="user",
        )

        assert result_query is query

    @staticmethod
    def test_apply_relations_filters_skips_none_values_and_returns_same_query():
        repository = UserProfileBaseRepository(session=AsyncMock())
        query = select(UserProfileTest)

        result_query = repository._apply_relations_filters(
            query,
            relations_filters={"name": None},
            relation="user",
        )

        assert result_query is query

    @staticmethod
    def test_build_filter_predicate_uses_plural_relation_fallback():
        repository = UserBaseRepository(session=AsyncMock())
        predicate = Mock()

        with patch.object(
            repository,
            "_build_relation_predicate",
            side_effect=[None, predicate],
        ):
            result = repository._build_filter_predicate(
                User,
                "user",
                "alice",
                {"id"},
            )

        assert result is predicate

    @staticmethod
    def test_apply_relations_filters_uses_valid_column_fallback_when_predicate_is_none():
        repository = UserProfileBaseRepository(session=AsyncMock())
        query = select(UserProfileTest)

        with patch.object(repository, "_build_relation_predicate", return_value=None):
            result_query = repository._apply_relations_filters(
                query,
                relations_filters={"name": "alice"},
                relation="user",
            )

        assert result_query is not query
        assert "users.name" in str(result_query)

    @staticmethod
    def test_apply_relations_filters_returns_same_query_when_no_predicates_generated():
        repository = UserProfileBaseRepository(session=AsyncMock())
        query = select(UserProfileTest)

        result_query = repository._apply_relations_filters(
            query,
            relations_filters={"not_a_column": "value"},
            relation="user",
        )

        assert result_query is query

    @staticmethod
    def test_apply_relations_filters_uses_any_for_uselist_relation():
        repository = RoleBaseRepository(session=AsyncMock())
        query = select(Role)

        result_query = repository._apply_relations_filters(
            query,
            relations_filters={"name": "alice"},
            relation="users",
        )

        assert result_query is not query
        assert ".name" in str(result_query)


class TestBaseRepositoryTotal:
    @staticmethod
    @pytest.mark.asyncio
    async def test_total_returns_count_from_scalar():
        expected_total = 10
        mock_session = AsyncMock()
        mock_session.scalar = AsyncMock(return_value=expected_total)

        repository = UserBaseRepository(session=mock_session)
        result = await repository.total()

        assert result == expected_total
        mock_session.scalar.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_total_returns_zero_when_scalar_is_none():
        mock_session = AsyncMock()
        mock_session.scalar = AsyncMock(return_value=None)

        repository = UserBaseRepository(session=mock_session)
        result = await repository.total()

        assert result == 0
        mock_session.scalar.assert_awaited_once()


class TestBaseRepositoryPersist:
    @staticmethod
    @pytest.mark.asyncio
    async def test_save_adds_commits_and_refreshes_entity():
        entity = object()
        mock_session = AsyncMock()

        repository = UserBaseRepository(session=mock_session)
        result = await repository.save(entity)

        assert result is entity
        mock_session.add.assert_called_once_with(entity)
        mock_session.commit.assert_awaited_once()
        mock_session.refresh.assert_awaited_once_with(entity)

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_merges_commits_and_refreshes_entity():
        entity = object()
        merged_entity = object()
        mock_session = AsyncMock()
        mock_session.merge = AsyncMock(return_value=merged_entity)

        repository = UserBaseRepository(session=mock_session)
        result = await repository.update(entity)

        assert result is merged_entity
        mock_session.merge.assert_awaited_once_with(entity)
        mock_session.commit.assert_awaited_once()
        mock_session.refresh.assert_awaited_once_with(merged_entity)


class TestBaseRepositoryListAll:
    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_returns_all_items_when_not_paginated():
        expected_items = ["alice", "bob"]
        scalars_result = Mock()
        scalars_result.all.return_value = expected_items

        mock_session = AsyncMock()
        mock_session.scalars = AsyncMock(return_value=scalars_result)

        repository = UserBaseRepository(session=mock_session)

        with patch("app.core.repository.base.is_paginate", return_value=False):
            result = await repository.list_all()

        assert result == expected_items
        mock_session.scalars.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_uses_paginate_when_page_filter_is_valid():
        result_limit = 50
        params = LimitOffsetParams(
            limit=1,
            offset=0,
        )
        expected_page = LimitOffsetPage.create(items=["alice"], total=1, params=params)
        mock_session = AsyncMock()
        repository = UserBaseRepository(session=mock_session)
        page_filter = FilterPage(offset=0, limit=50)

        with (
            patch("app.core.repository.base.is_paginate", return_value=True),
            patch(
                "app.core.repository.base.get_limit_offset_params",
                return_value=LimitOffsetParams(limit=50, offset=0),
            ),
            patch(
                "app.core.repository.base.paginate", new_callable=AsyncMock
            ) as paginate_mock,
        ):
            paginate_mock.return_value = expected_page
            result = await repository.list_all(page_filter=page_filter)

        assert result.items == ["alice"]
        assert result.meta.total == 1
        assert result.meta.limit == result_limit
        assert result.meta.offset == 0
        paginate_mock.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_returns_custom_paginate_directly_when_paginate_already_matches():
        params = LimitOffsetParams(limit=50, offset=0)
        expected_page = CustomLimitOffsetPage.create(
            items=["alice"],
            total=1,
            params=params,
        )
        mock_session = AsyncMock()
        repository = UserBaseRepository(session=mock_session)
        page_filter = FilterPage(offset=0, limit=50)

        with (
            patch("app.core.repository.base.is_paginate", return_value=True),
            patch(
                "app.core.repository.base.get_limit_offset_params",
                return_value=params,
            ),
            patch(
                "app.core.repository.base.paginate", new_callable=AsyncMock
            ) as paginate_mock,
        ):
            paginate_mock.return_value = expected_page
            result = await repository.list_all(page_filter=page_filter)

        assert result is expected_page

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_uses_paginate_meta_total_when_total_attr_is_missing():
        params = LimitOffsetParams(limit=50, offset=0)
        paginate_result = types.SimpleNamespace(
            items=["alice"],
            meta=types.SimpleNamespace(total=1),
        )
        mock_session = AsyncMock()
        repository = UserBaseRepository(session=mock_session)
        page_filter = FilterPage(offset=0, limit=50)

        with (
            patch("app.core.repository.base.is_paginate", return_value=True),
            patch(
                "app.core.repository.base.get_limit_offset_params",
                return_value=params,
            ),
            patch(
                "app.core.repository.base.paginate", new_callable=AsyncMock
            ) as paginate_mock,
        ):
            paginate_mock.return_value = paginate_result
            result = await repository.list_all(page_filter=page_filter)

        assert result.items == ["alice"]
        assert result.meta.total == 1

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_applies_filter_by_from_page_filter():
        expected_items = ["alice"]
        scalars_result = Mock()
        scalars_result.all.return_value = expected_items

        mock_session = AsyncMock()
        mock_session.scalars = AsyncMock(return_value=scalars_result)

        repository = UserBaseRepository(session=mock_session)

        with patch("app.core.repository.base.is_paginate", return_value=False):
            result = await repository.list_all(
                page_filter=FilterPage.build(name="alice")
            )

        query = mock_session.scalars.await_args.args[0]

        assert result == expected_items
        assert "users.name" in str(query)

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_applies_model_filter_with_relational_order_by():
        expected_items = ["user-item"]
        scalars_result = Mock()
        scalars_result.all.return_value = expected_items

        mock_session = AsyncMock()
        mock_session.scalars = AsyncMock(return_value=scalars_result)

        repository = UserProfileBaseRepository(session=mock_session)
        repository.default_order_by = "user.role.name"

        with patch("app.core.repository.base.is_paginate", return_value=False):
            result = await repository.list_all(
                page_filter=FilterPage.build(account_id="account-id")
            )

        query = mock_session.scalars.await_args.args[0]

        assert result == expected_items
        assert "user_profiles_test.account_id" in str(query)
        assert "ORDER BY roles.name" in str(query)

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_applies_user_role_relation_filter():
        expected_items = ["user-item"]
        scalars_result = Mock()
        scalars_result.all.return_value = expected_items

        mock_session = AsyncMock()
        mock_session.scalars = AsyncMock(return_value=scalars_result)

        repository = UserProfileBaseRepository(session=mock_session)

        with patch("app.core.repository.base.is_paginate", return_value=False):
            result = await repository.list_all(
                page_filter=FilterPage.build(user_role="admin")
            )

        query = mock_session.scalars.await_args.args[0]
        query_str = str(query)

        assert result == expected_items
        assert ".name" in query_str

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_uses_manual_paginate_path_when_relations_filter_exists():
        expected_items = ["alice"]
        scalars_result = Mock()
        scalars_result.all.return_value = expected_items

        mock_session = AsyncMock()
        mock_session.scalar = AsyncMock(return_value=1)
        mock_session.scalars = AsyncMock(return_value=scalars_result)

        repository = UserProfileBaseRepository(session=mock_session)
        repository.relations = (selectinload(UserProfileTest.user),)
        page_filter = FilterPage.build(user_name="alice", offset=0, limit=10)

        with (
            patch("app.core.repository.base.is_paginate", return_value=True),
            patch(
                "app.core.repository.base.get_limit_offset_params",
                return_value=LimitOffsetParams(limit=10, offset=0),
            ),
            patch(
                "app.core.repository.base.paginate",
                new_callable=AsyncMock,
            ) as paginate_mock,
        ):
            result = await repository.list_all(page_filter=page_filter)

        assert result.items == expected_items
        mock_session.scalar.assert_awaited_once()
        mock_session.scalars.assert_awaited_once()
        paginate_mock.assert_not_awaited()


class TestBaseRepositoryFindBy:
    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_calls_filter_by_with_kwargs_and_returns_scalar_result():
        expected_entity = types.SimpleNamespace(name="alice")
        mock_session = AsyncMock()
        mock_session.scalar = AsyncMock(return_value=expected_entity)

        repository = UserBaseRepository(session=mock_session)
        result = await repository.find_by(name="alice")

        assert result == expected_entity
        mock_session.scalar.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_returns_none_when_no_valid_filters_are_provided():
        mock_session = AsyncMock()
        repository = UserBaseRepository(session=mock_session)

        result = await repository.find_by(name=None, order=None)

        assert result is None
        mock_session.scalar.assert_not_called()

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_aply_special_user_name_filter_when_model_has_user_relation():
        expected_entity = types.SimpleNamespace(id="user-id")
        mock_session = AsyncMock()
        mock_session.scalar = AsyncMock(return_value=expected_entity)

        repository = UserProfileBaseRepository(session=mock_session)

        result = await repository.find_by(account_id="account-id", user_name="alice")
        query = mock_session.scalar.await_args.args[0]

        assert result == expected_entity
        assert "users.name" in str(query)
        assert "user_profiles_test.account_id" in str(query)

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_ignores_empty_and_none_relation_filters():
        mock_session = AsyncMock()
        repository = UserProfileBaseRepository(session=mock_session)

        result = await repository.find_by(user_="ignored", user_name=None)

        assert result is None
        mock_session.scalar.assert_not_called()

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_returns_none_when_one_of_filters_no_valid():
        mock_session = AsyncMock()
        expected_entity = types.SimpleNamespace(name="alice")
        mock_session.scalar = AsyncMock(return_value=expected_entity)
        repository = UserProfileBaseRepository(session=mock_session)

        result = await repository.find_by(account_id=uuid4(), name="bob")

        assert result is None
        mock_session.scalar.assert_not_called()
