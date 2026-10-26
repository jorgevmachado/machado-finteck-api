from http import HTTPStatus
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.domain.institution.repository import InstitutionRepository
from app.domain.institution.schema import (
    InstitutionCreateSchema,
    InstitutionUpdateSchema,
)
from app.domain.institution.service import InstitutionService
from app.shared.schemas import FilterPage, Message


class TestInstitutionServiceResolve:
    @staticmethod
    def test_from_session_binds_repository():
        session = AsyncMock()
        service = InstitutionService.from_session(session)

        assert isinstance(service.repository, InstitutionRepository)
        assert service.repository.session is session

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("exists", [False, True])
    async def test_resolve_normalizes_lookup_and_creates_only_when_missing(
        user, institution, exists
    ):
        service = InstitutionService(AsyncMock())
        service.find_by = AsyncMock(return_value=institution if exists else None)
        service.create = AsyncMock(return_value=institution)

        result = await service.resolve(user, "  Electric Company  ")

        assert result is institution
        service.find_by.assert_awaited_once_with(
            user_id=user.id, name_code="electric_company", without_throw=True
        )
        if exists:
            service.create.assert_not_awaited()
        else:
            service.create.assert_awaited_once_with(
                user=user, payload=InstitutionCreateSchema(name="Electric Company")
            )

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("failed_method", ["find_by", "create"])
    async def test_resolve_propagates_lookup_and_creation_failures(user, failed_method):
        service = InstitutionService(AsyncMock())
        service.find_by = AsyncMock(return_value=None)
        service.create = AsyncMock()
        exception = HTTPException(HTTPStatus.SERVICE_UNAVAILABLE, "Service unavailable")
        getattr(service, failed_method).side_effect = exception

        with pytest.raises(HTTPException) as caught:
            await service.resolve(user, "Electric Company")

        assert caught.value is exception
        if failed_method == "find_by":
            service.create.assert_not_awaited()


class TestInstitutionServiceList:
    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_scopes_results_to_authenticated_user(user):
        repository = AsyncMock()
        repository.list_all.return_value = []

        result = await InstitutionService(repository).list_all(FilterPage(), user)

        assert result == []
        filters = repository.list_all.await_args.kwargs["page_filter"]
        assert filters.user_id == user.id

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_reports_repository_failure(user):
        repository = AsyncMock()
        repository.list_all.side_effect = RuntimeError("database failure")

        with pytest.raises(HTTPException) as exc:
            await InstitutionService(repository).list_all(FilterPage(), user)

        assert exc.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


class TestInstitutionServiceCreate:
    @staticmethod
    @pytest.mark.asyncio
    async def test_create_normalizes_name_and_assigns_owner(
        user, institution, create_institution_payload
    ):
        repository = AsyncMock()
        repository.find_by.return_value = None
        repository.save.return_value = institution
        service = InstitutionService(repository)
        service._invalidate_cache = AsyncMock()

        result = await service.create(user, create_institution_payload)

        assert result is institution
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
        user, institution, create_institution_payload
    ):
        repository = AsyncMock()
        repository.find_by.return_value = institution

        with pytest.raises(HTTPException) as exc:
            await InstitutionService(repository).create(
                user, create_institution_payload
            )

        assert exc.value.status_code == HTTPStatus.CONFLICT
        assert exc.value.detail == "Institution already exists"
        repository.save.assert_not_awaited()


class TestInstitutionServiceFind:
    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_uses_owner_filter(user, institution):
        repository = AsyncMock()
        repository.find_by.return_value = institution

        result = await InstitutionService(repository).find_by(
            id=institution.id, user_id=user.id
        )

        assert result is institution
        repository.find_by.assert_awaited_once_with(
            id=institution.id, name_code=None, user_id=user.id
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_rejects_missing_or_foreign_institution(user):
        repository = AsyncMock()
        repository.find_by.return_value = None

        with pytest.raises(HTTPException) as exc:
            await InstitutionService(repository).find_by(id=uuid4(), user_id=user.id)

        assert exc.value.status_code == HTTPStatus.NOT_FOUND


class TestInstitutionServiceUpdate:
    @staticmethod
    @pytest.mark.asyncio
    async def test_update_returns_not_found_when_lookup_returns_none(
        user, update_institution_payload
    ):
        repository = AsyncMock()
        service = InstitutionService(repository)
        service.find_by = AsyncMock(return_value=None)
        service._invalidate_cache = AsyncMock()
        institution_id = str(uuid4())

        with pytest.raises(HTTPException) as exc:
            await service.update(institution_id, update_institution_payload, user)

        assert exc.value.status_code == HTTPStatus.NOT_FOUND
        assert exc.value.detail == "Institution not found"
        service.find_by.assert_awaited_once_with(
            id=institution_id, user_id=user.id, user_request=user.username
        )
        repository.update.assert_not_awaited()
        service._invalidate_cache.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_changes_name_and_normalized_code(
        user, institution, update_institution_payload
    ):
        repository = AsyncMock()
        service = InstitutionService(repository)
        service.find_by = AsyncMock(side_effect=[institution, institution])
        service._invalidate_cache = AsyncMock()

        result = await service.update(
            str(institution.id), update_institution_payload, user
        )

        assert isinstance(result, Message)
        assert institution.name == "Water Company"
        assert institution.name_code == "water_company"
        repository.update.assert_awaited_once_with(entity=institution)
        service._invalidate_cache.assert_awaited_once_with(
            identifier=str(institution.id)
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_rejects_name_owned_by_another_institution(
        user, institution, update_institution_payload
    ):
        duplicate = AsyncMock()
        duplicate.id = uuid4()
        service = InstitutionService(AsyncMock())
        service.find_by = AsyncMock(side_effect=[institution, duplicate])

        with pytest.raises(HTTPException) as exc:
            await service.update(str(institution.id), update_institution_payload, user)

        assert exc.value.status_code == HTTPStatus.CONFLICT
        service.repository.update.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_empty_update_preserves_entity(user, institution):
        repository = AsyncMock()
        service = InstitutionService(repository)
        service.find_by = AsyncMock(return_value=institution)
        service._invalidate_cache = AsyncMock()
        original_name = institution.name

        await service.update(str(institution.id), InstitutionUpdateSchema(), user)

        assert institution.name == original_name
        repository.update.assert_awaited_once_with(entity=institution)


class TestInstitutionServiceDelete:
    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_removes_only_owned_institution(user, institution):
        repository = AsyncMock()
        repository.find_by.return_value = institution
        service = InstitutionService(repository)
        service._invalidate_cache = AsyncMock()

        result = await service.delete(user, str(institution.id))

        assert isinstance(result, Message)
        repository.find_by.assert_awaited_once_with(
            id=str(institution.id), name_code=None, user_id=user.id
        )
        repository.delete.assert_awaited_once_with(entity=institution)
        service._invalidate_cache.assert_awaited_once_with(
            identifier=str(institution.id)
        )

    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_rejects_missing_or_foreign_institution(user):
        repository = AsyncMock()
        repository.find_by.return_value = None

        with pytest.raises(HTTPException) as exc:
            await InstitutionService(repository).delete(user, str(uuid4()))

        assert exc.value.status_code == HTTPStatus.NOT_FOUND
        repository.delete.assert_not_awaited()


class TestInstitutionServiceCache:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("identifier", [None, "institution-id"])
    async def test_invalidate_cache_clears_domain_and_namespaced_key(identifier):
        service = InstitutionService(AsyncMock())
        service.cache_service = Mock()
        service.cache_service.delete_with_parent_cache = AsyncMock()
        service.cache_service.cache.delete_cache = AsyncMock()
        service.cache_service.build_key_one.return_value = "institution:institution-id"

        await service._invalidate_cache(identifier)

        service.cache_service.delete_with_parent_cache.assert_awaited_once_with()
        if identifier:
            service.cache_service.build_key_one.assert_called_once_with(
                param=identifier
            )
            service.cache_service.cache.delete_cache.assert_awaited_once_with(
                "institution:institution-id"
            )
        else:
            service.cache_service.cache.delete_cache.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_failure_is_logged_without_blocking_database_update(
        user, institution, update_institution_payload, caplog
    ):
        repository = AsyncMock()
        repository.find_by.return_value = institution
        service = InstitutionService(repository)
        service.cache_service.delete_with_parent_cache = AsyncMock(
            side_effect=RuntimeError("cache unavailable")
        )

        result = await service.update(
            str(institution.id), update_institution_payload, user
        )

        assert isinstance(result, Message)
        repository.update.assert_awaited_once_with(entity=institution)
        assert "Cache invalidation skipped" in caplog.text
