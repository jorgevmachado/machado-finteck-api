from http import HTTPStatus
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.domain.beneficiary.schema import BeneficiaryUpdateSchema
from app.domain.beneficiary.service import BeneficiaryService
from app.shared.schemas import FilterPage, Message


class TestBeneficiaryServiceList:
    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_scopes_results_to_authenticated_user(user):
        repository = AsyncMock()
        repository.list_all.return_value = []

        result = await BeneficiaryService(repository).list_all(FilterPage(), user)

        assert result == []
        filters = repository.list_all.await_args.kwargs["page_filter"]
        assert filters.user_id == user.id

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_reports_repository_failure(user):
        repository = AsyncMock()
        repository.list_all.side_effect = RuntimeError("database failure")

        with pytest.raises(HTTPException) as exc:
            await BeneficiaryService(repository).list_all(FilterPage(), user)

        assert exc.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


class TestBeneficiaryServiceCreate:
    @staticmethod
    @pytest.mark.asyncio
    async def test_create_normalizes_name_and_assigns_owner(
        user, beneficiary, create_beneficiary_payload
    ):
        repository = AsyncMock()
        repository.find_by.return_value = None
        repository.save.return_value = beneficiary
        service = BeneficiaryService(repository)
        service._invalidate_cache = AsyncMock()

        result = await service.create(user, create_beneficiary_payload)

        assert result is beneficiary
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
        user, beneficiary, create_beneficiary_payload
    ):
        repository = AsyncMock()
        repository.find_by.return_value = beneficiary

        with pytest.raises(HTTPException) as exc:
            await BeneficiaryService(repository).create(user, create_beneficiary_payload)

        assert exc.value.status_code == HTTPStatus.CONFLICT
        assert exc.value.detail == "Beneficiary already exists"
        repository.save.assert_not_awaited()


class TestBeneficiaryServiceFind:
    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_uses_owner_filter(user, beneficiary):
        repository = AsyncMock()
        repository.find_by.return_value = beneficiary

        result = await BeneficiaryService(repository).find_by(
            id=beneficiary.id, user_id=user.id
        )

        assert result is beneficiary
        repository.find_by.assert_awaited_once_with(
            id=beneficiary.id, name_code=None, user_id=user.id
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_rejects_missing_or_foreign_beneficiary(user):
        repository = AsyncMock()
        repository.find_by.return_value = None

        with pytest.raises(HTTPException) as exc:
            await BeneficiaryService(repository).find_by(id=uuid4(), user_id=user.id)

        assert exc.value.status_code == HTTPStatus.NOT_FOUND


class TestBeneficiaryServiceUpdate:
    @staticmethod
    @pytest.mark.asyncio
    async def test_update_returns_not_found_when_lookup_returns_none(
        user, update_beneficiary_payload
    ):
        repository = AsyncMock()
        service = BeneficiaryService(repository)
        service.find_by = AsyncMock(return_value=None)
        service._invalidate_cache = AsyncMock()
        beneficiary_id = str(uuid4())

        with pytest.raises(HTTPException) as exc:
            await service.update(beneficiary_id, update_beneficiary_payload, user)

        assert exc.value.status_code == HTTPStatus.NOT_FOUND
        assert exc.value.detail == "Beneficiary not found"
        service.find_by.assert_awaited_once_with(
            id=beneficiary_id, user_id=user.id, user_request=user.username
        )
        repository.update.assert_not_awaited()
        service._invalidate_cache.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_changes_name_and_normalized_code(
        user, beneficiary, update_beneficiary_payload
    ):
        repository = AsyncMock()
        service = BeneficiaryService(repository)
        service.find_by = AsyncMock(side_effect=[beneficiary, beneficiary])
        service._invalidate_cache = AsyncMock()

        result = await service.update(str(beneficiary.id), update_beneficiary_payload, user)

        assert isinstance(result, Message)
        assert beneficiary.name == "Water Company"
        assert beneficiary.name_code == "water_company"
        repository.update.assert_awaited_once_with(entity=beneficiary)
        service._invalidate_cache.assert_awaited_once_with(identifier=str(beneficiary.id))

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_rejects_name_owned_by_another_beneficiary(
        user, beneficiary, update_beneficiary_payload
    ):
        duplicate = AsyncMock()
        duplicate.id = uuid4()
        service = BeneficiaryService(AsyncMock())
        service.find_by = AsyncMock(side_effect=[beneficiary, duplicate])

        with pytest.raises(HTTPException) as exc:
            await service.update(str(beneficiary.id), update_beneficiary_payload, user)

        assert exc.value.status_code == HTTPStatus.CONFLICT
        service.repository.update.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_empty_update_preserves_entity(user, beneficiary):
        repository = AsyncMock()
        service = BeneficiaryService(repository)
        service.find_by = AsyncMock(return_value=beneficiary)
        service._invalidate_cache = AsyncMock()
        original_name = beneficiary.name

        await service.update(str(beneficiary.id), BeneficiaryUpdateSchema(), user)

        assert beneficiary.name == original_name
        repository.update.assert_awaited_once_with(entity=beneficiary)


class TestBeneficiaryServiceDelete:
    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_removes_only_owned_beneficiary(user, beneficiary):
        repository = AsyncMock()
        repository.find_by.return_value = beneficiary
        service = BeneficiaryService(repository)
        service._invalidate_cache = AsyncMock()

        result = await service.delete(user, str(beneficiary.id))

        assert isinstance(result, Message)
        repository.find_by.assert_awaited_once_with(
            id=str(beneficiary.id), name_code=None, user_id=user.id
        )
        repository.delete.assert_awaited_once_with(entity=beneficiary)
        service._invalidate_cache.assert_awaited_once_with(identifier=str(beneficiary.id))

    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_rejects_missing_or_foreign_beneficiary(user):
        repository = AsyncMock()
        repository.find_by.return_value = None

        with pytest.raises(HTTPException) as exc:
            await BeneficiaryService(repository).delete(user, str(uuid4()))

        assert exc.value.status_code == HTTPStatus.NOT_FOUND
        repository.delete.assert_not_awaited()


class TestBeneficiaryServiceCache:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("identifier", [None, "beneficiary-id"])
    async def test_invalidate_cache_clears_domain_and_namespaced_key(identifier):
        service = BeneficiaryService(AsyncMock())
        service.cache_service = Mock()
        service.cache_service.delete_with_parent_cache = AsyncMock()
        service.cache_service.cache.delete_cache = AsyncMock()
        service.cache_service.build_key_one.return_value = "beneficiary:beneficiary-id"

        await service._invalidate_cache(identifier)

        service.cache_service.delete_with_parent_cache.assert_awaited_once_with()
        if identifier:
            service.cache_service.build_key_one.assert_called_once_with(
                param=identifier
            )
            service.cache_service.cache.delete_cache.assert_awaited_once_with(
                "beneficiary:beneficiary-id"
            )
        else:
            service.cache_service.cache.delete_cache.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_failure_is_logged_without_blocking_database_update(
        user, beneficiary, update_beneficiary_payload, caplog
    ):
        repository = AsyncMock()
        repository.find_by.return_value = beneficiary
        service = BeneficiaryService(repository)
        service.cache_service.delete_with_parent_cache = AsyncMock(
            side_effect=RuntimeError("cache unavailable")
        )

        result = await service.update(str(beneficiary.id), update_beneficiary_payload, user)

        assert isinstance(result, Message)
        repository.update.assert_awaited_once_with(entity=beneficiary)
        assert "Cache invalidation skipped" in caplog.text
