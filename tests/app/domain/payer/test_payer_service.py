from http import HTTPStatus
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.domain.payer.schema import PayerUpdateSchema
from app.domain.payer.service import PayerService
from app.shared.schemas import FilterPage, Message


class TestPayerServiceList:
    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_scopes_results_to_authenticated_user(user):
        repository = AsyncMock()
        repository.list_all.return_value = []

        result = await PayerService(repository).list_all(FilterPage(), user)

        assert result == []
        filters = repository.list_all.await_args.kwargs["page_filter"]
        assert filters.user_id == user.id

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_reports_repository_failure(user):
        repository = AsyncMock()
        repository.list_all.side_effect = RuntimeError("database failure")

        with pytest.raises(HTTPException) as exc:
            await PayerService(repository).list_all(FilterPage(), user)

        assert exc.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


class TestPayerServiceCreate:
    @staticmethod
    @pytest.mark.asyncio
    async def test_create_normalizes_name_and_assigns_owner(
        user, payer, create_payer_payload
    ):
        repository = AsyncMock()
        repository.find_by.return_value = None
        repository.save.return_value = payer
        service = PayerService(repository)
        service._invalidate_cache = AsyncMock()

        result = await service.create(user, create_payer_payload)

        assert result is payer
        repository.find_by.assert_awaited_once_with(
            id=None, name_code="electric_company", user_id=user.id
        )
        entity = repository.save.await_args.kwargs["entity"]
        assert entity.user_id == user.id
        assert entity.name == "Electric Company"
        assert entity.name_code == "electric_company"
        service._invalidate_cache.assert_awaited_once_with()

    @staticmethod
    @pytest.mark.asyncio
    async def test_create_rejects_normalized_duplicate(
        user, payer, create_payer_payload
    ):
        repository = AsyncMock()
        repository.find_by.return_value = payer

        with pytest.raises(HTTPException) as exc:
            await PayerService(repository).create(user, create_payer_payload)

        assert exc.value.status_code == HTTPStatus.CONFLICT
        assert exc.value.detail == "Payer already exists"
        repository.save.assert_not_awaited()


class TestPayerServiceFind:
    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_uses_owner_filter(user, payer):
        repository = AsyncMock()
        repository.find_by.return_value = payer

        result = await PayerService(repository).find_by(
            id=payer.id, user_id=user.id
        )

        assert result is payer
        repository.find_by.assert_awaited_once_with(
            id=payer.id, name_code=None, user_id=user.id
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_rejects_missing_or_foreign_payer(user):
        repository = AsyncMock()
        repository.find_by.return_value = None

        with pytest.raises(HTTPException) as exc:
            await PayerService(repository).find_by(id=uuid4(), user_id=user.id)

        assert exc.value.status_code == HTTPStatus.NOT_FOUND


class TestPayerServiceUpdate:
    @staticmethod
    @pytest.mark.asyncio
    async def test_update_returns_not_found_when_lookup_returns_none(
        user, update_payer_payload
    ):
        repository = AsyncMock()
        service = PayerService(repository)
        service.find_by = AsyncMock(return_value=None)
        service._invalidate_cache = AsyncMock()
        payer_id = str(uuid4())

        with pytest.raises(HTTPException) as exc:
            await service.update(payer_id, update_payer_payload, user)

        assert exc.value.status_code == HTTPStatus.NOT_FOUND
        assert exc.value.detail == "Payer not found"
        service.find_by.assert_awaited_once_with(
            id=payer_id, user_id=user.id, user_request=user.username
        )
        repository.update.assert_not_awaited()
        service._invalidate_cache.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_changes_name_and_normalized_code(
        user, payer, update_payer_payload
    ):
        repository = AsyncMock()
        service = PayerService(repository)
        service.find_by = AsyncMock(side_effect=[payer, payer])
        service._invalidate_cache = AsyncMock()

        result = await service.update(str(payer.id), update_payer_payload, user)

        assert isinstance(result, Message)
        assert payer.name == "Water Company"
        assert payer.name_code == "water_company"
        repository.update.assert_awaited_once_with(entity=payer)
        service._invalidate_cache.assert_awaited_once_with(identifier=str(payer.id))

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_rejects_name_owned_by_another_payer(
        user, payer, update_payer_payload
    ):
        duplicate = AsyncMock()
        duplicate.id = uuid4()
        service = PayerService(AsyncMock())
        service.find_by = AsyncMock(side_effect=[payer, duplicate])

        with pytest.raises(HTTPException) as exc:
            await service.update(str(payer.id), update_payer_payload, user)

        assert exc.value.status_code == HTTPStatus.CONFLICT
        service.repository.update.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_empty_update_preserves_entity(user, payer):
        repository = AsyncMock()
        service = PayerService(repository)
        service.find_by = AsyncMock(return_value=payer)
        service._invalidate_cache = AsyncMock()
        original_name = payer.name

        await service.update(str(payer.id), PayerUpdateSchema(), user)

        assert payer.name == original_name
        repository.update.assert_awaited_once_with(entity=payer)


class TestPayerServiceDelete:
    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_removes_only_owned_payer(user, payer):
        repository = AsyncMock()
        repository.find_by.return_value = payer
        service = PayerService(repository)
        service._invalidate_cache = AsyncMock()

        result = await service.delete(user, str(payer.id))

        assert isinstance(result, Message)
        repository.find_by.assert_awaited_once_with(
            id=str(payer.id), name_code=None, user_id=user.id
        )
        repository.delete.assert_awaited_once_with(entity=payer)
        service._invalidate_cache.assert_awaited_once_with(identifier=str(payer.id))

    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_rejects_missing_or_foreign_payer(user):
        repository = AsyncMock()
        repository.find_by.return_value = None

        with pytest.raises(HTTPException) as exc:
            await PayerService(repository).delete(user, str(uuid4()))

        assert exc.value.status_code == HTTPStatus.NOT_FOUND
        repository.delete.assert_not_awaited()


class TestPayerServiceCache:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("identifier", [None, "payer-id"])
    async def test_invalidate_cache_clears_domain_and_namespaced_key(identifier):
        service = PayerService(AsyncMock())
        service.cache_service = Mock()
        service.cache_service.delete_with_parent_cache = AsyncMock()
        service.cache_service.cache.delete_cache = AsyncMock()
        service.cache_service.build_key_one.return_value = "payer:payer-id"

        await service._invalidate_cache(identifier)

        service.cache_service.delete_with_parent_cache.assert_awaited_once_with()
        if identifier:
            service.cache_service.build_key_one.assert_called_once_with(
                param=identifier
            )
            service.cache_service.cache.delete_cache.assert_awaited_once_with(
                "payer:payer-id"
            )
        else:
            service.cache_service.cache.delete_cache.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_failure_is_logged_without_blocking_database_update(
        user, payer, update_payer_payload, caplog
    ):
        repository = AsyncMock()
        repository.find_by.return_value = payer
        service = PayerService(repository)
        service.cache_service.delete_with_parent_cache = AsyncMock(
            side_effect=RuntimeError("cache unavailable")
        )

        result = await service.update(str(payer.id), update_payer_payload, user)

        assert isinstance(result, Message)
        repository.update.assert_awaited_once_with(entity=payer)
        assert "Cache invalidation skipped" in caplog.text
