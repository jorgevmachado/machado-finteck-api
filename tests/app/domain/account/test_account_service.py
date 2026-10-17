from http import HTTPStatus
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.domain.account.service import AccountService
from app.domain.account.schema import AccountUpdateSchema
from app.domain.account.repository import AccountRepository
from app.domain.account.route import find_one
from app.shared.schemas import FilterPage, Message


class TestAccountService:
    @staticmethod
    def test_from_session_builds_service():
        service = AccountService.from_session(AsyncMock())

        assert isinstance(service, AccountService)
        assert AccountService.__bases__ == (object,)


class TestAccountServiceList:
    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_returns_empty_list_when_user_has_no_accounts(user):
        repository = AsyncMock()
        repository.list_all.return_value = []

        result = await AccountService(repository).list_all(FilterPage(), user)

        assert result == []
        filters = repository.list_all.await_args.kwargs["page_filter"]
        assert filters.user_id == user.id

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_does_not_hide_repository_failure(user):
        repository = AsyncMock()
        repository.list_all.side_effect = RuntimeError("database failure")

        with pytest.raises(HTTPException) as exc:
            await AccountService(repository).list_all(FilterPage(), user)

        assert exc.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert exc.value.detail == "Internal server error"

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_filters_accounts_by_authenticated_user(user):
        repository = AsyncMock()
        service = AccountService(repository)
        page_filter = FilterPage.build(name="Daily")

        result = await service.list_all(page_filter=page_filter, user=user)

        assert result == repository.list_all.return_value
        repository.list_all.assert_awaited_once()
        filters = repository.list_all.await_args.kwargs["page_filter"]
        assert filters.name == "Daily"
        assert filters.user_id == user.id

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_overrides_client_supplied_user_filter(user):
        repository = AsyncMock()
        service = AccountService(repository)
        another_user_id = "not-the-authenticated-user"
        page_filter = FilterPage.build(user_id=another_user_id)

        await service.list_all(page_filter=page_filter, user=user)

        filters = repository.list_all.await_args.kwargs["page_filter"]
        assert filters.user_id == user.id


class TestAccountServiceCreate:
    @staticmethod
    @pytest.mark.asyncio
    async def test_create_checks_duplicate_name_only_within_authenticated_user(
        user, account, create_account_payload
    ):
        repository = AsyncMock()
        repository.find_by.return_value = None
        repository.save.return_value = account

        result = await AccountService(repository).create(user, create_account_payload)

        assert result is account
        repository.find_by.assert_awaited_once_with(
            id=None, name=create_account_payload.name, user_id=user.id
        )
        repository.save.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_create_account_with_all_fields(
        user, account, create_account_payload
    ):
        repository = AsyncMock()
        service = AccountService(repository)

        service.find_by = AsyncMock(return_value=None)

        repository.save.return_value = account

        result = await service.create(user, create_account_payload)

        assert result == account
        saved_entity = repository.save.await_args.kwargs["entity"]
        assert saved_entity.user_id == user.id
        assert saved_entity.icon == create_account_payload.icon
        assert saved_entity.type == create_account_payload.type
        assert saved_entity.name == create_account_payload.name
        assert saved_entity.color == create_account_payload.color
        assert saved_entity.agency == create_account_payload.agency
        assert saved_entity.is_active == create_account_payload.is_active
        assert saved_entity.description == create_account_payload.description
        assert saved_entity.account_number == create_account_payload.account_number
        assert (
            saved_entity.financial_institution
            == create_account_payload.financial_institution
        )
        service.find_by.assert_awaited_once_with(
            user_id=user.id,
            name=create_account_payload.name,
            without_throw=True,
        )
        repository.save.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_create_rejects_duplicate_account(
        user, account, create_account_payload
    ):
        repository = AsyncMock()
        service = AccountService(repository)
        service.find_by = AsyncMock(return_value=account)

        with pytest.raises(HTTPException) as exc:
            await service.create(user, create_account_payload)

        assert exc.value.status_code == HTTPStatus.CONFLICT
        assert exc.value.detail == "Account already exists"
        repository.save.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_create_handles_repository_exception(user, create_account_payload):
        repository = AsyncMock()
        repository.save.side_effect = RuntimeError("database failure")
        service = AccountService(repository)
        service.find_by = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await service.create(user, create_account_payload)

        assert exc.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert exc.value.detail == "Internal server error"
        repository.save.assert_awaited_once()


class TestAccountServiceUpdate:
    @staticmethod
    @pytest.mark.asyncio
    async def test_partial_update_preserves_omitted_name_and_type(user, account):
        repository = AsyncMock()
        repository.find_by.return_value = account
        service = AccountService(repository)
        service._invalidate_cache = AsyncMock()
        original_name, original_type = account.name, account.type

        await service.update(str(account.id), AccountUpdateSchema(color="Blue"), user)

        assert account.color == "Blue"
        assert account.name == original_name
        assert account.type == original_type
        repository.update.assert_awaited_once_with(entity=account)

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_account_requires_matching_owner(
        user, account, update_account_payload
    ):
        repository = AsyncMock()
        repository.update.return_value = account
        service = AccountService(repository)
        service.find_by = AsyncMock(return_value=account)
        service._invalidate_cache = AsyncMock()

        result = await service.update(
            param=str(account.id),
            update_schema=update_account_payload,
            user=user,
        )

        assert isinstance(result, Message)
        service.find_by.assert_awaited_once_with(
            id=str(account.id), user_id=user.id, user_request=user.username
        )
        repository.update.assert_awaited_once_with(entity=account)
        service._invalidate_cache.assert_awaited_once_with(identifier=str(account.id))
        assert account.name == update_account_payload.name

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_account_returns_not_found_for_another_users_account(
        user, account, update_account_payload
    ):
        repository = AsyncMock()
        service = AccountService(repository)
        service.find_by = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await service.update(
                param=str(account.id),
                update_schema=update_account_payload,
                user=user,
            )

        assert exc.value.status_code == HTTPStatus.NOT_FOUND
        assert exc.value.detail == "Account not found"
        service.find_by.assert_awaited_once_with(
            id=str(account.id), user_id=user.id, user_request=user.username
        )
        repository.update.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_uses_real_lookup_without_logging_metadata(
        user, account, update_account_payload
    ):
        session = AsyncMock()
        session.scalar.return_value = account
        service = AccountService(AccountRepository(session))
        service._invalidate_cache = AsyncMock()
        service.repository.update = AsyncMock()
        update_account_payload.name = "Updated account"

        result = await service.update(
            param=str(account.id), update_schema=update_account_payload, user=user
        )

        assert isinstance(result, Message)
        session.scalar.assert_awaited_once()
        params = session.scalar.await_args.args[0].compile().params
        assert set(params.values()) == {str(account.id), user.id}
        assert account.name == "Updated account"
        service.repository.update.assert_awaited_once_with(entity=account)

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_reports_repository_failure(
        user, account, update_account_payload
    ):
        repository = AsyncMock()
        repository.find_by.return_value = account
        repository.update.side_effect = RuntimeError("database failure")
        service = AccountService(repository)
        service._invalidate_cache = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await service.update(str(account.id), update_account_payload, user)

        assert exc.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


class TestAccountServiceFindBy:
    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_does_not_pass_logging_or_control_flags_to_repository(
        user, account
    ):
        repository = AsyncMock()
        repository.find_by.return_value = account

        result = await AccountService(repository).find_by(
            id=account.id,
            user_id=user.id,
            user_request=user.username,
            without_throw=True,
        )

        assert result is account
        repository.find_by.assert_awaited_once_with(
            id=account.id, name=None, user_id=user.id
        )

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("found", [True, False])
    async def test_get_account_reaches_database_with_owner_filter(user, account, found):
        session = AsyncMock()
        session.scalar.return_value = account if found else None
        service = AccountService(AccountRepository(session))

        if found:
            result = await find_one(str(account.id), service, user)
            assert result is account
        else:
            with pytest.raises(HTTPException) as exc:
                await find_one(str(account.id), service, user)
            assert exc.value.status_code == HTTPStatus.NOT_FOUND

        session.scalar.assert_awaited_once()
        query = session.scalar.await_args.args[0]
        assert "accounts.id =" in str(query)
        assert "accounts.user_id =" in str(query)
        assert set(query.compile().params.values()) == {str(account.id), user.id}

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_returns_none_only_for_optional_missing_account(user):
        repository = AsyncMock()
        repository.find_by.return_value = None

        result = await AccountService(repository).find_by(
            name="Missing", user_id=user.id, without_throw=True
        )

        assert result is None
        repository.find_by.assert_awaited_once_with(
            id=None, name="Missing", user_id=user.id
        )

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("without_throw", [True, False])
    async def test_find_by_does_not_hide_database_failures(user, without_throw):
        repository = AsyncMock()
        repository.find_by.side_effect = RuntimeError("database failure")

        with pytest.raises(HTTPException) as exc:
            await AccountService(repository).find_by(
                id=uuid4(), user_id=user.id, without_throw=without_throw
            )

        assert exc.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


class TestAccountServiceDelete:
    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_reports_database_failure(user, account):
        repository = AsyncMock()
        repository.find_by.return_value = account
        repository.delete.side_effect = RuntimeError("database failure")

        with pytest.raises(HTTPException) as exc:
            await AccountService(repository).delete(user, str(account.id))

        assert exc.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert exc.value.detail == "Internal server error"

    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_queries_owner_before_removing_account(user, account):
        repository = AsyncMock()
        repository.find_by.return_value = account

        result = await AccountService(repository).delete(user, str(account.id))

        assert isinstance(result, Message)
        repository.find_by.assert_awaited_once_with(
            id=str(account.id), name=None, user_id=user.id
        )
        repository.delete.assert_awaited_once_with(entity=account)

    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_rejects_missing_or_foreign_account(user):
        repository = AsyncMock()
        repository.find_by.return_value = None

        with pytest.raises(HTTPException) as exc:
            await AccountService(repository).delete(user, str(uuid4()))

        assert exc.value.status_code == HTTPStatus.NOT_FOUND
        repository.delete.assert_not_awaited()


class TestAccountServiceCache:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("identifier", [None, "account-id"])
    async def test_invalidate_cache_clears_domain_and_namespaced_key(identifier):
        service = AccountService(AsyncMock())
        service.cache_service = Mock()
        service.cache_service.delete_with_parent_cache = AsyncMock()
        service.cache_service.cache.delete_cache = AsyncMock()
        service.cache_service.build_key_one.return_value = "account:account-id"

        await service._invalidate_cache(identifier)

        service.cache_service.delete_with_parent_cache.assert_awaited_once_with()
        if identifier:
            service.cache_service.build_key_one.assert_called_once_with(
                param=identifier
            )
            service.cache_service.cache.delete_cache.assert_awaited_once_with(
                "account:account-id"
            )
        else:
            service.cache_service.cache.delete_cache.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_failure_is_logged_without_blocking_database_update(
        user, account, update_account_payload, caplog
    ):
        repository = AsyncMock()
        repository.find_by.return_value = account
        service = AccountService(repository)
        service.cache_service.delete_with_parent_cache = AsyncMock(
            side_effect=RuntimeError("cache unavailable")
        )

        result = await service.update(str(account.id), update_account_payload, user)

        assert isinstance(result, Message)
        repository.update.assert_awaited_once_with(entity=account)
        assert "Cache invalidation skipped" in caplog.text


@pytest.mark.asyncio
async def test_failed_create_does_not_log_success(user, create_account_payload):
    repository = AsyncMock()
    repository.find_by.side_effect = RuntimeError("database failure")
    service = AccountService(repository)

    with patch("app.domain.account.service.log_service_success") as log_success:
        with pytest.raises(HTTPException):
            await service.create(user, create_account_payload)

    log_success.assert_not_called()
    repository.save.assert_not_awaited()
