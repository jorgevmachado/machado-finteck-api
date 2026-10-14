from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict

from app.core.logging import LoggingParams
from app.core.service.base import BaseService
from app.models import utcnow
from app.shared.schemas import FilterPage


class BaseModelSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    value: int


class SourceBaseModelSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    source: str
    source_code: str


@pytest.fixture
def mock_repository():
    repo = MagicMock()
    repo.list_all = AsyncMock()
    repo.find_by = AsyncMock()
    return repo


@pytest.fixture
def logger_params():
    return LoggingParams(
        logger=MagicMock(),
        service="test_service",
        operation="test_operation",
    )


@pytest.fixture
def base_service(mock_repository, logger_params):
    service = BaseService(
        "test_service", mock_repository, logger_params, BaseModelSchema
    )
    return service


MOCK_RESULT = {"id": "123e4567-e89b-12d3-a456-426614174000", "name": "name"}


class TestBaseServiceListAll:
    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_success(base_service, mock_repository):
        mock_repository.list_all.return_value = ["item1", "item2"]
        filter_page = FilterPage(limit=10, offset=1)
        with patch("app.core.service.base.log_service_success") as mock_log_success:
            result = await base_service.list_all(
                page_filter=filter_page, user_request="user1"
            )
            assert result == ["item1", "item2"]
            mock_repository.list_all.assert_awaited_once_with(page_filter=filter_page)
            mock_log_success.assert_called_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_exception(base_service, mock_repository):
        mock_repository.list_all.side_effect = Exception("Repo error")
        filter_page = FilterPage(limit=10, offset=1)
        with (
            patch("app.core.service.base.handle_service_exception") as mock_handle_exc,
            patch("app.core.service.base.log_service_success") as mock_log_success,
        ):
            result = await base_service.list_all(
                page_filter=filter_page, user_request="user2"
            )
            assert hasattr(result, "items")
            assert hasattr(result, "meta")
            meta = result.meta
            assert meta.total == 0
            assert result.items == []
            assert meta.limit == filter_page.limit
            assert meta.offset == filter_page.offset
            mock_handle_exc.assert_called_once()
            mock_log_success.assert_called_once()


class TestFilterPageHelpers:
    @staticmethod
    def test_filter_page_with_updates_supports_dynamic_fields():
        page_filter = FilterPage(page=1)

        updated = page_filter.with_updates(clean_cache=True)

        assert updated.page == 1
        assert updated.clean_cache is True
        assert updated.model_dump(exclude_none=True)["clean_cache"] is True


class TestBaseServiceListAllCached:
    @staticmethod
    @pytest.mark.asyncio
    async def test_base_service_list_all_cached_success(base_service, mock_repository):
        values = [
            BaseModelSchema(id="1", name="item1", value=1),
            BaseModelSchema(id="2", name="item2", value=2),
        ]
        page_filter = FilterPage(clean_cache=True)
        base_service.cache_service.delete_domain = AsyncMock()
        base_service.cache_service.build_key_list = AsyncMock(
            return_value="test_service:list"
        )
        base_service.cache_service.get_list = AsyncMock(return_value=values)

        result = await base_service.list_all_cached(
            page_filter=page_filter,
            user_request="user1",
        )
        assert isinstance(result, list)
        assert len(result) == len(values)
        assert page_filter.clean_cache is None
        base_service.cache_service.delete_domain.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_base_service_list_all_cached_not_cached(
        base_service, mock_repository
    ):
        values = [
            BaseModelSchema(id="1", name="item1", value=1),
            BaseModelSchema(id="2", name="item2", value=2),
        ]
        with patch(
            "app.core.cache.redis.redis_client", new_callable=AsyncMock
        ) as mock_redis_client:
            mock_redis_client.setex.return_value = None
            base_service.cache_service.build_key_list = AsyncMock(
                return_value="test_service:list"
            )
            base_service.cache_service.get_list = AsyncMock(return_value=None)
            base_service.list_all = AsyncMock(return_value=values)

            with patch(
                "app.core.cache.manager.CacheManager.set_cache", new_callable=AsyncMock
            ) as mock_set_cache:
                mock_set_cache.return_value = None
                result = await base_service.list_all_cached(user_request="user2")
                assert isinstance(result, list)
                assert len(result) == len(values)


class TestBaseServiceFindOne:
    @staticmethod
    @pytest.mark.asyncio
    async def test_find_one_by_name_success(base_service, mock_repository):
        mock_repository.find_by.return_value = MOCK_RESULT
        result = await base_service.find_one(param=MOCK_RESULT["name"])
        assert result["id"] == MOCK_RESULT["id"]
        assert result["name"] == MOCK_RESULT["name"]
        mock_repository.find_by.assert_awaited_once_with(
            name=MOCK_RESULT["name"], with_deleted=False
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_one_by_id_success(base_service, mock_repository):
        mock_repository.find_by.return_value = MOCK_RESULT
        result = await base_service.find_one(param=MOCK_RESULT["id"])
        assert result["id"] == MOCK_RESULT["id"]
        assert result["name"] == MOCK_RESULT["name"]
        mock_repository.find_by.assert_awaited_once_with(
            id=MOCK_RESULT["id"], with_deleted=False
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_one_by_id_with_reference_year(base_service, mock_repository):
        mock_repository.find_by.return_value = MOCK_RESULT
        result = await base_service.find_one(
            param=MOCK_RESULT["id"], with_deleted=False, reference_year=2023
        )
        assert result["id"] == MOCK_RESULT["id"]
        assert result["name"] == MOCK_RESULT["name"]
        mock_repository.find_by.assert_awaited_once_with(
            id=MOCK_RESULT["id"], with_deleted=False, reference_year=2023
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_one_not_found(base_service, mock_repository):
        mock_repository.find_by.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            await base_service.find_one(param="not_found")
        assert exc_info.value.status_code == HTTPStatus.NOT_FOUND
        assert exc_info.value.detail == "test_service not found"


class TestBaseServiceFindOneCached:
    """Test scope for fetch_one_cached method"""

    @staticmethod
    @pytest.mark.asyncio
    async def test_base_service_find_one_cached_success(base_service, mock_repository):
        """Should return complete pokemon when found"""
        item = BaseModelSchema(id="1", name="item1", value=1)
        mock_repository.find_by.return_value = item
        base_service.cache_service.build_key_one = AsyncMock(
            return_value=f"test_service:{item.name}"
        )
        base_service.cache_service.get_one = AsyncMock(return_value=item)
        result = await base_service.find_one_cached(
            param=item.name, user_request="user1"
        )
        assert result is not None
        assert result.id == item.id
        assert result.name == item.name
        assert result.value == item.value

    @staticmethod
    @pytest.mark.asyncio
    async def test_base_service_find_one_cached_not_cached(
        base_service, mock_repository
    ):
        item = BaseModelSchema(id="1", name="item1", value=1)
        with patch(
            "app.core.cache.redis.redis_client", new_callable=AsyncMock
        ) as mock_redis_client:
            mock_redis_client.setex.return_value = None
            base_service.cache_service.build_key_one = AsyncMock(
                return_value=f"test_service:{item.name}"
            )
            base_service.cache_service.get_one = AsyncMock(return_value=None)

            base_service.find_one = AsyncMock(return_value=item)

            with patch(
                "app.core.cache.manager.CacheManager.set_cache", new_callable=AsyncMock
            ) as mock_set_cache:
                mock_set_cache.return_value = None
                result = await base_service.find_one_cached(
                    param=item.name, user_request="user2"
                )
                assert result is not None
                assert result.id == item.id
                assert result.name == item.name
                assert result.value == item.value

    @staticmethod
    @pytest.mark.asyncio
    async def test_base_service_find_one_cached_with_clean_cache(base_service):
        item = BaseModelSchema(id="1", name="item1", value=1)
        cache_key = "test_service:item1"
        base_service.cache_service.build_key_one = MagicMock(return_value=cache_key)
        base_service.cache_service.cache.delete_cache = AsyncMock(return_value=None)
        base_service.cache_service.get_one = AsyncMock(return_value=item)

        result = await base_service.find_one_cached(
            param=item.name,
            user_request="user1",
            clean_cache=True,
        )

        assert result == item
        base_service.cache_service.cache.delete_cache.assert_awaited_once_with(
            cache_key
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_base_service_find_one_cached_success_with_reference_year(
        base_service, mock_repository
    ):
        """Should return complete pokemon when found"""
        reference_year = utcnow().year
        item = BaseModelSchema(id="1", name="item1", value=1)
        mock_repository.find_by.return_value = item
        base_service.cache_service.build_key_one = AsyncMock(
            return_value=f"test_service:{item.name}:{reference_year}"
        )
        base_service.cache_service.get_one = AsyncMock(return_value=item)
        result = await base_service.find_one_cached(
            param=item.name, user_request="user1", reference_year=reference_year
        )
        assert result is not None
        assert result.id == item.id
        assert result.name == item.name
        assert result.value == item.value


class TestBaseServiceFindBy:
    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_success(base_service, mock_repository):
        mock_repository.find_by.return_value = MOCK_RESULT
        result = await base_service.find_by(name=MOCK_RESULT["name"])
        assert result["id"] == MOCK_RESULT["id"]
        assert result["name"] == MOCK_RESULT["name"]
        mock_repository.find_by.assert_awaited_once_with(name=MOCK_RESULT["name"])

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_not_found(base_service, mock_repository):
        mock_repository.find_by.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            await base_service.find_by(name=MOCK_RESULT["name"])
        assert exc_info.value.status_code == HTTPStatus.NOT_FOUND
        assert exc_info.value.detail == "test_service not found"


class MockUpdateSchema:
    def __init__(self, data):
        self._data = data

    def model_dump(self, exclude_unset=True):
        return self._data


class MockNameUpdateSchema(MockUpdateSchema):
    model_fields = {"name": object(), "name_code": object()}


class MockSourceUpdateSchema(MockUpdateSchema):
    model_fields = {"source": object(), "source_code": object()}


class TestBaseServiceUpdate:
    @staticmethod
    @pytest.mark.asyncio
    async def test_update_success(base_service, mock_repository):
        entity = {"id": "123", "name": "old_name", "value": 1}
        mock_repository.find_by.return_value = entity
        mock_repository.update = AsyncMock(
            return_value={**entity, "name": "new_name", "value": 2}
        )
        base_service._invalidate_cache = AsyncMock(return_value=None)
        update_data = {"name": "new_name", "value": 2}
        update_schema = MockUpdateSchema(update_data)
        with patch("app.core.service.base.log_service_success"):
            result = await base_service.update(param="123", update_schema=update_schema)
            assert result["name"] == "new_name"
            assert result["value"] == update_data["value"]
        mock_repository.update.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_object_entity_success(base_service, mock_repository):
        entity = BaseModelSchema(id="1", name="old", value=1)
        mock_repository.find_by.return_value = entity
        mock_repository.update = AsyncMock(return_value=entity)
        base_service._invalidate_cache = AsyncMock(return_value=None)

        update_schema = MockUpdateSchema({"name": "new", "value": 2})
        result = await base_service.update("old", update_schema)

        assert result.name == "new"
        assert result.value == 2

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_partial_success(base_service, mock_repository):
        entity = {"id": "123", "name": "old_name", "value": 1}
        mock_repository.find_by.return_value = entity
        mock_repository.update = AsyncMock(
            return_value={**entity, "name": "partial_update"}
        )
        base_service._invalidate_cache = AsyncMock(return_value=None)
        update_data = {"name": "partial_update"}
        update_schema = MockUpdateSchema(update_data)
        with patch("app.core.service.base.log_service_success") as mock_log_success:
            result = await base_service.update(param="123", update_schema=update_schema)
            assert result["name"] == "partial_update"
            assert result["value"] == 1
            mock_repository.update.assert_awaited_once()
            mock_log_success.assert_any_call(
                base_service.logger_params,
                operation="update",
                message=f"Update {base_service.alias} successfully",
                user_request=None,
            )

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_syncs_name_code_when_name_changes(
        base_service, mock_repository
    ):
        entity = {
            "id": "123",
            "name": "old name",
            "name_code": "old_name",
            "value": 1,
        }
        mock_repository.find_by.return_value = entity
        mock_repository.update = AsyncMock(return_value=entity)
        base_service._invalidate_cache = AsyncMock(return_value=None)

        update_schema = MockNameUpdateSchema({"name": "New Name", "value": 2})

        with patch("app.core.service.base.log_service_success"):
            await base_service.update(param="123", update_schema=update_schema)

        updated_entity = mock_repository.update.await_args.args[0]
        assert updated_entity["name"] == "New Name"
        assert updated_entity["name_code"] == "new_name"

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_syncs_source_code_when_source_changes(
        base_service, mock_repository
    ):
        entity = SourceBaseModelSchema(
            id="1",
            source="Old Source",
            source_code="old_source",
        )
        mock_repository.find_by.return_value = entity
        mock_repository.update = AsyncMock(return_value=entity)
        base_service._invalidate_cache = AsyncMock(return_value=None)

        update_schema = MockSourceUpdateSchema({"source": "New Source"})

        with patch("app.core.service.base.log_service_success"):
            await base_service.update(param="1", update_schema=update_schema)

        updated_entity = mock_repository.update.await_args.args[0]
        assert updated_entity.source == "New Source"
        assert updated_entity.source_code == "new_source"

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_skips_name_code_when_name_is_not_string(
        base_service, mock_repository
    ):
        entity = {
            "id": "123",
            "name": "old name",
            "name_code": "old_name",
            "value": 1,
        }
        mock_repository.find_by.return_value = entity
        mock_repository.update = AsyncMock(return_value=entity)
        base_service._invalidate_cache = AsyncMock(return_value=None)

        update_schema = MockNameUpdateSchema({"name": 123})

        with patch("app.core.service.base.log_service_success"):
            await base_service.update(param="123", update_schema=update_schema)

        updated_entity = mock_repository.update.await_args.args[0]
        assert updated_entity["name"] == 123
        assert updated_entity["name_code"] == "old_name"

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_not_found(base_service, mock_repository):
        base_service.find_one = AsyncMock(return_value=None)
        update_schema = MockUpdateSchema({"name": "irrelevant"})
        with pytest.raises(HTTPException) as exc_info:
            await base_service.update(param="not_found", update_schema=update_schema)
        assert exc_info.value.status_code == HTTPStatus.NOT_FOUND
        assert "not found" in str(exc_info.value.detail)

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_exception(base_service, mock_repository):
        entity = {"id": "123", "name": "old_name"}
        mock_repository.find_by.return_value = entity
        mock_repository.update = AsyncMock(side_effect=Exception("DB error"))
        base_service._invalidate_cache = AsyncMock(return_value=None)
        update_schema = MockUpdateSchema({"name": "fail_update"})
        with (
            patch("app.core.service.base.handle_service_exception") as mock_handle_exc,
            patch("app.core.service.base.log_service_success") as mock_log_success,
        ):
            await base_service.update(param="123", update_schema=update_schema)
            mock_handle_exc.assert_called_once()
            # Verifica se a chamada de update foi feita
            mock_log_success.assert_any_call(
                base_service.logger_params,
                operation="update",
                message=f"Update {base_service.alias} successfully",
                user_request=None,
            )


class TestBaseServiceListAllCachedNoPageFilter:
    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_cached_no_page_filter_no_cache(base_service):
        values = [
            BaseModelSchema(id="1", name="item1", value=1),
            BaseModelSchema(id="2", name="item2", value=2),
        ]
        base_service.cache_service.build_key_list = AsyncMock(
            return_value="test_service:list"
        )
        base_service.cache_service.get_list = AsyncMock(return_value=None)
        base_service.cache_service.set_list = AsyncMock()
        base_service.list_all = AsyncMock(return_value=values)

        result = await base_service.list_all_cached(
            page_filter=None, user_request="user3"
        )
        assert isinstance(result, list)
        assert len(result) == len(values)
        base_service.cache_service.set_list.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_cached_with_trainer_id(base_service):
        values = [
            BaseModelSchema(id="1", name="item1", value=1),
        ]
        base_service.cache_service.build_key_list = AsyncMock(
            return_value="test_service:trainer:list"
        )
        base_service.cache_service.get_list = AsyncMock(return_value=None)
        base_service.cache_service.set_list = AsyncMock()
        base_service.list_all = AsyncMock(return_value=values)

        result = await base_service.list_all_cached(
            page_filter=None, user_request="user4", finance_id="trainer123"
        )
        assert isinstance(result, list)
        assert len(result) == 1


class TestBaseServiceInvalidateCache:
    @staticmethod
    @pytest.mark.asyncio
    async def test_invalidate_cache_with_identifier_and_trainer(base_service):
        base_service.cache_service.delete_domain = AsyncMock()
        base_service.cache_service.cache.delete_cache = AsyncMock()

        await base_service._invalidate_cache(
            identifier="item1", finance_id="trainer123"
        )

        base_service.cache_service.delete_domain.assert_awaited_once()
        base_service.cache_service.cache.delete_cache.assert_awaited_once_with(
            "trainer123:item1"
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_invalidate_cache_with_identifier_only(base_service):
        base_service.cache_service.delete_domain = AsyncMock()
        base_service.cache_service.cache.delete_cache = AsyncMock()

        await base_service._invalidate_cache(identifier="item1")

        base_service.cache_service.delete_domain.assert_awaited_once()
        base_service.cache_service.cache.delete_cache.assert_awaited_once_with("item1")

    @staticmethod
    @pytest.mark.asyncio
    async def test_invalidate_cache_no_identifier(base_service):
        base_service.cache_service.delete_domain = AsyncMock()
        base_service.cache_service.cache.delete_cache = AsyncMock()

        await base_service._invalidate_cache()

        base_service.cache_service.delete_domain.assert_awaited_once()
        base_service.cache_service.cache.delete_cache.assert_not_awaited()


class TestBaseServiceFindOneByName:
    @staticmethod
    @pytest.mark.asyncio
    async def test_find_one_by_name(base_service, mock_repository):
        entity = BaseModelSchema(id="123", name="test_name", value=100)
        mock_repository.find_by.return_value = entity
        with patch("app.core.service.base.log_service_success") as mock_log_success:
            result = await base_service.find_one(
                param="test_name", user_request="user1"
            )
            assert result == entity
            mock_repository.find_by.assert_awaited_once_with(
                name="test_name", with_deleted=None
            )
            mock_log_success.assert_called_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_one_by_name_with_trainer_id(base_service, mock_repository):
        entity = BaseModelSchema(id="123", name="test_name", value=100)
        mock_repository.find_by.return_value = entity
        with patch("app.core.service.base.log_service_success") as mock_log_success:
            result = await base_service.find_one(
                param="test_name", user_request="user2", finance_id="trainer123"
            )
            assert result == entity
            mock_repository.find_by.assert_awaited_once_with(
                name="test_name", finance_id="trainer123", with_deleted=None
            )
            mock_log_success.assert_called_once()


class TestBaseServiceFindOneCache:
    @staticmethod
    @pytest.mark.asyncio
    async def test_find_one_cached_with_trainer_id(base_service):
        entity = BaseModelSchema(id="1", name="item", value=50)
        base_service.cache_service.build_key_one = AsyncMock(
            return_value="trainer123:item"
        )
        base_service.cache_service.get_one = AsyncMock(return_value=None)
        base_service.cache_service.set_one = AsyncMock()
        base_service.find_one = AsyncMock(return_value=entity)

        result = await base_service.find_one_cached(
            param="item", user_request="user1", finance_id="trainer123"
        )
        assert result == entity
        base_service.cache_service.set_one.assert_awaited_once()


class TestBaseServiceUpdateEntity:
    @staticmethod
    @pytest.mark.asyncio
    async def test_update_entity_success(base_service, mock_repository):
        entity = {"id": "123", "name": "pikachu"}
        mock_repository.update = AsyncMock(return_value=entity)

        with patch("app.core.service.base.log_service_success") as mock_log_success:
            result = await base_service.update_entity(entity=entity, user_request="ash")

        assert result is entity
        mock_repository.update.assert_awaited_once_with(entity=entity)
        mock_log_success.assert_called_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_entity_handles_exception(base_service, mock_repository):
        entity = {"id": "123", "name": "pikachu"}
        mock_repository.update = AsyncMock(side_effect=Exception("db-error"))

        with (
            patch("app.core.service.base.handle_service_exception") as mock_handle_exc,
            patch("app.core.service.base.log_service_success") as mock_log_success,
        ):
            await base_service.update_entity(entity=entity, user_request="ash")

        mock_handle_exc.assert_called_once()
        mock_log_success.assert_called_once()


class TestBaseServiceSoftDelete:
    @staticmethod
    @pytest.mark.asyncio
    async def test_soft_delete_success(base_service, mock_repository):
        entity = MagicMock()
        entity.deleted_at = None
        base_service.find_one = AsyncMock(return_value=entity)
        base_service._invalidate_cache = AsyncMock(return_value=None)
        mock_repository.update = AsyncMock(return_value=entity)

        result = await base_service.soft_delete(
            param="item", user_request="user1", finance_id="finance-1"
        )

        assert result.message == "Deleted test_service successfully"
        base_service.find_one.assert_awaited_once_with(
            param="item", finance_id="finance-1", user_request="user1"
        )
        base_service._invalidate_cache.assert_awaited_once_with(
            identifier="item", finance_id="finance-1"
        )
        mock_repository.update.assert_awaited_once_with(entity)
        assert entity.deleted_at is not None

    @staticmethod
    @pytest.mark.asyncio
    async def test_soft_delete_handles_not_found(base_service):
        base_service.find_one = AsyncMock(return_value=None)

        with (
            patch("app.core.service.base.handle_service_exception") as mock_handle_exc,
            patch("app.core.service.base.log_service_success") as mock_log_success,
        ):
            result = await base_service.soft_delete(
                param="missing", user_request="user2", finance_id="finance-1"
            )

        assert result is None
        mock_handle_exc.assert_called_once()
        mock_log_success.assert_called_once()
