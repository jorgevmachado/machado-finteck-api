from http import HTTPStatus
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.domain.credit_card.service import CreditCardService
from app.domain.credit_card.schema import CreditCardUpdateSchema
from app.domain.credit_card.repository import CreditCardRepository
from app.domain.credit_card.route import find_one
from app.shared.schemas import FilterPage, Message


class TestCreditCardService:
    @staticmethod
    def test_from_session_builds_service():
        service = CreditCardService.from_session(AsyncMock())

        assert isinstance(service, CreditCardService)
        assert CreditCardService.__bases__ == (object,)


class TestCreditCardServiceList:
    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_returns_empty_list_when_user_has_no_credit_cards(user):
        repository = AsyncMock()
        repository.list_all.return_value = []

        result = await CreditCardService(repository).list_all(FilterPage(), user)

        assert result == []
        filters = repository.list_all.await_args.kwargs["page_filter"]
        assert filters.user_id == user.id

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_does_not_hide_repository_failure(user):
        repository = AsyncMock()
        repository.list_all.side_effect = RuntimeError("database failure")

        with pytest.raises(HTTPException) as exc:
            await CreditCardService(repository).list_all(FilterPage(), user)

        assert exc.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert exc.value.detail == "Internal server error"

    @staticmethod
    @pytest.mark.asyncio
    async def test_list_all_filters_credit_cards_by_authenticated_user(user):
        repository = AsyncMock()
        service = CreditCardService(repository)
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
        service = CreditCardService(repository)
        another_user_id = "not-the-authenticated-user"
        page_filter = FilterPage.build(user_id=another_user_id)

        await service.list_all(page_filter=page_filter, user=user)

        filters = repository.list_all.await_args.kwargs["page_filter"]
        assert filters.user_id == user.id


class TestCreditCardServiceCreate:
    @staticmethod
    @pytest.mark.asyncio
    async def test_create_checks_duplicate_name_only_within_authenticated_user(
        user, credit_card, create_credit_card_payload
    ):
        repository = AsyncMock()
        repository.find_by.return_value = None
        repository.save.return_value = credit_card

        result = await CreditCardService(repository).create(user, create_credit_card_payload)

        assert result is credit_card
        repository.find_by.assert_awaited_once_with(
            id=None, name=create_credit_card_payload.name, user_id=user.id
        )
        repository.save.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_create_credit_card_with_all_fields(
        user, credit_card, create_credit_card_payload
    ):
        repository = AsyncMock()
        service = CreditCardService(repository)

        service.find_by = AsyncMock(return_value=None)

        repository.save.return_value = credit_card

        result = await service.create(user, create_credit_card_payload)

        assert result == credit_card
        saved_entity = repository.save.await_args.kwargs["entity"]
        assert saved_entity.user_id == user.id
        assert saved_entity.icon == create_credit_card_payload.icon
        assert saved_entity.brand == create_credit_card_payload.brand
        assert saved_entity.name == create_credit_card_payload.name
        assert saved_entity.color == create_credit_card_payload.color
        assert saved_entity.due_day == create_credit_card_payload.due_day
        assert saved_entity.closing_day == create_credit_card_payload.closing_day
        assert saved_entity.is_active == create_credit_card_payload.is_active
        assert saved_entity.description == create_credit_card_payload.description
        assert saved_entity.last_four_digits == create_credit_card_payload.last_four_digits

        service.find_by.assert_awaited_once_with(
            user_id=user.id,
            name=create_credit_card_payload.name,
            without_throw=True,
        )
        repository.save.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_create_rejects_duplicate_credit_card(
        user, credit_card, create_credit_card_payload
    ):
        repository = AsyncMock()
        service = CreditCardService(repository)
        service.find_by = AsyncMock(return_value=credit_card)

        with pytest.raises(HTTPException) as exc:
            await service.create(user, create_credit_card_payload)

        assert exc.value.status_code == HTTPStatus.CONFLICT
        assert exc.value.detail == "CreditCard already exists"
        repository.save.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_create_handles_repository_exception(user, create_credit_card_payload):
        repository = AsyncMock()
        repository.save.side_effect = RuntimeError("database failure")
        service = CreditCardService(repository)
        service.find_by = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await service.create(user, create_credit_card_payload)

        assert exc.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert exc.value.detail == "Internal server error"
        repository.save.assert_awaited_once()


class TestCreditCardServiceUpdate:
    @staticmethod
    @pytest.mark.asyncio
    async def test_partial_update_preserves_omitted_name_and_brand(user, credit_card):
        repository = AsyncMock()
        repository.find_by.return_value = credit_card
        service = CreditCardService(repository)
        service._invalidate_cache = AsyncMock()
        original_name, original_brand = credit_card.name, credit_card.brand

        await service.update(str(credit_card.id), CreditCardUpdateSchema(color="Blue"), user)

        assert credit_card.color == "Blue"
        assert credit_card.name == original_name
        assert credit_card.brand == original_brand
        repository.update.assert_awaited_once_with(entity=credit_card)

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_credit_card_requires_matching_owner(
        user, credit_card, update_credit_card_payload
    ):
        repository = AsyncMock()
        repository.update.return_value = credit_card
        service = CreditCardService(repository)
        service.find_by = AsyncMock(return_value=credit_card)
        service._invalidate_cache = AsyncMock()

        result = await service.update(
            param=str(credit_card.id),
            update_schema=update_credit_card_payload,
            user=user,
        )

        assert isinstance(result, Message)
        service.find_by.assert_awaited_once_with(
            id=str(credit_card.id), user_id=user.id, user_request=user.username
        )
        repository.update.assert_awaited_once_with(entity=credit_card)
        service._invalidate_cache.assert_awaited_once_with(identifier=str(credit_card.id))
        assert credit_card.name == update_credit_card_payload.name

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_credit_card_returns_not_found_for_another_users_credit_card(
        user, credit_card, update_credit_card_payload
    ):
        repository = AsyncMock()
        service = CreditCardService(repository)
        service.find_by = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await service.update(
                param=str(credit_card.id),
                update_schema=update_credit_card_payload,
                user=user,
            )

        assert exc.value.status_code == HTTPStatus.NOT_FOUND
        assert exc.value.detail == "CreditCard not found"
        service.find_by.assert_awaited_once_with(
            id=str(credit_card.id), user_id=user.id, user_request=user.username
        )
        repository.update.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_uses_real_lookup_without_logging_metadata(
        user, credit_card, update_credit_card_payload
    ):
        session = AsyncMock()
        session.scalar.return_value = credit_card
        service = CreditCardService(CreditCardRepository(session))
        service._invalidate_cache = AsyncMock()
        service.repository.update = AsyncMock()
        update_credit_card_payload.name = "Updated credit_card"

        result = await service.update(
            param=str(credit_card.id), update_schema=update_credit_card_payload, user=user
        )

        assert isinstance(result, Message)
        session.scalar.assert_awaited_once()
        params = session.scalar.await_args.args[0].compile().params
        assert set(params.values()) == {str(credit_card.id), user.id}
        assert credit_card.name == "Updated credit_card"
        service.repository.update.assert_awaited_once_with(entity=credit_card)

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_reports_repository_failure(
        user, credit_card, update_credit_card_payload
    ):
        repository = AsyncMock()
        repository.find_by.return_value = credit_card
        repository.update.side_effect = RuntimeError("database failure")
        service = CreditCardService(repository)
        service._invalidate_cache = AsyncMock()

        with pytest.raises(HTTPException) as exc:
            await service.update(str(credit_card.id), update_credit_card_payload, user)

        assert exc.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


class TestCreditCardServiceFindBy:
    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_does_not_pass_logging_or_control_flags_to_repository(
        user, credit_card
    ):
        repository = AsyncMock()
        repository.find_by.return_value = credit_card

        result = await CreditCardService(repository).find_by(
            id=credit_card.id,
            user_id=user.id,
            user_request=user.username,
            without_throw=True,
        )

        assert result is credit_card
        repository.find_by.assert_awaited_once_with(
            id=credit_card.id, name=None, user_id=user.id
        )

    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("found", [True, False])
    async def test_get_credit_card_reaches_database_with_owner_filter(user, credit_card, found):
        session = AsyncMock()
        session.scalar.return_value = credit_card if found else None
        service = CreditCardService(CreditCardRepository(session))

        if found:
            result = await find_one(str(credit_card.id), service, user)
            assert result is credit_card
        else:
            with pytest.raises(HTTPException) as exc:
                await find_one(str(credit_card.id), service, user)
            assert exc.value.status_code == HTTPStatus.NOT_FOUND

        session.scalar.assert_awaited_once()
        query = session.scalar.await_args.args[0]
        assert "credit_cards.id =" in str(query)
        assert "credit_cards.user_id =" in str(query)
        assert set(query.compile().params.values()) == {str(credit_card.id), user.id}

    @staticmethod
    @pytest.mark.asyncio
    async def test_find_by_returns_none_only_for_optional_missing_credit_card(user):
        repository = AsyncMock()
        repository.find_by.return_value = None

        result = await CreditCardService(repository).find_by(
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
            await CreditCardService(repository).find_by(
                id=uuid4(), user_id=user.id, without_throw=without_throw
            )

        assert exc.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR


class TestCreditCardServiceDelete:
    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_reports_database_failure(user, credit_card):
        repository = AsyncMock()
        repository.find_by.return_value = credit_card
        repository.delete.side_effect = RuntimeError("database failure")

        with pytest.raises(HTTPException) as exc:
            await CreditCardService(repository).delete(user, str(credit_card.id))

        assert exc.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert exc.value.detail == "Internal server error"

    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_queries_owner_before_removing_credit_card(user, credit_card):
        repository = AsyncMock()
        repository.find_by.return_value = credit_card

        result = await CreditCardService(repository).delete(user, str(credit_card.id))

        assert isinstance(result, Message)
        repository.find_by.assert_awaited_once_with(
            id=str(credit_card.id), name=None, user_id=user.id
        )
        repository.delete.assert_awaited_once_with(entity=credit_card)

    @staticmethod
    @pytest.mark.asyncio
    async def test_delete_rejects_missing_or_foreign_credit_card(user):
        repository = AsyncMock()
        repository.find_by.return_value = None

        with pytest.raises(HTTPException) as exc:
            await CreditCardService(repository).delete(user, str(uuid4()))

        assert exc.value.status_code == HTTPStatus.NOT_FOUND
        repository.delete.assert_not_awaited()


class TestCreditCardServiceCache:
    @staticmethod
    @pytest.mark.asyncio
    @pytest.mark.parametrize("identifier", [None, "credit_card-id"])
    async def test_invalidate_cache_clears_domain_and_namespaced_key(identifier):
        service = CreditCardService(AsyncMock())
        service.cache_service = Mock()
        service.cache_service.delete_with_parent_cache = AsyncMock()
        service.cache_service.cache.delete_cache = AsyncMock()
        service.cache_service.build_key_one.return_value = "credit_card:credit_card-id"

        await service._invalidate_cache(identifier)

        service.cache_service.delete_with_parent_cache.assert_awaited_once_with()
        if identifier:
            service.cache_service.build_key_one.assert_called_once_with(
                param=identifier
            )
            service.cache_service.cache.delete_cache.assert_awaited_once_with(
                "credit_card:credit_card-id"
            )
        else:
            service.cache_service.cache.delete_cache.assert_not_awaited()

    @staticmethod
    @pytest.mark.asyncio
    async def test_cache_failure_is_logged_without_blocking_database_update(
        user, credit_card, update_credit_card_payload, caplog
    ):
        repository = AsyncMock()
        repository.find_by.return_value = credit_card
        service = CreditCardService(repository)
        service.cache_service.delete_with_parent_cache = AsyncMock(
            side_effect=RuntimeError("cache unavailable")
        )

        result = await service.update(str(credit_card.id), update_credit_card_payload, user)

        assert isinstance(result, Message)
        repository.update.assert_awaited_once_with(entity=credit_card)
        assert "Cache invalidation skipped" in caplog.text


@pytest.mark.asyncio
async def test_failed_create_does_not_log_success(user, create_credit_card_payload):
    repository = AsyncMock()
    repository.find_by.side_effect = RuntimeError("database failure")
    service = CreditCardService(repository)

    with patch("app.domain.credit_card.service.log_service_success") as log_success:
        with pytest.raises(HTTPException):
            await service.create(user, create_credit_card_payload)

    log_success.assert_not_called()
    repository.save.assert_not_awaited()
