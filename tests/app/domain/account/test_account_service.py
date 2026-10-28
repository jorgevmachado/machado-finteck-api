from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.domain.account.repository import AccountRepository
from app.domain.account.schema import (
    AccountCreateSchema,
    AccountSchema,
    AccountUpdateSchema,
)
from app.domain.account.service import AccountService
from app.models import Account, AccountTypeEnum
from app.shared.schemas import FilterPage, Message
from app.temp import BaseService

pytestmark = pytest.mark.asyncio


def _create_payload(name: str, **overrides) -> AccountCreateSchema:
    return AccountCreateSchema(
        name=name,
        type=AccountTypeEnum.CASH,
        **overrides,
    )


def _account_entity(user_id, name, **overrides):
    return Account(
        user_id=user_id,
        name=name,
        type=AccountTypeEnum.CASH,
        icon=None,
        color=None,
        agency=None,
        description=None,
        account_number=None,
        financial_institution=None,
        is_active=True,
        **overrides,
    )


async def test_account_inherits_crud_without_redefining_it(service, account_session):
    assert isinstance(service.repository, AccountRepository)
    assert service.repository.session is account_session
    for method in ("list_all", "find_by", "create", "update", "delete"):
        assert getattr(AccountService, method) is getattr(BaseService, method)


async def test_crud_preserves_partial_update_and_deletes(
    service, user, create_account_payload, update_account_payload
):
    account = await service.create(user, create_account_payload)
    identifier = str(account.id)
    assert account.user_id == user.id
    assert account.name == "Test Account"
    assert account.type == AccountTypeEnum.CASH
    assert await service.find_by(user=user, filters={"id": identifier}) is account
    assert await service.list_all(FilterPage(), user) == [account]
    result = await service.update(identifier, update_account_payload, user)
    assert isinstance(result, Message)
    assert result.message == f"Update Account {identifier} successfully"
    assert account.name == "Test Account"
    await service.update(identifier, AccountUpdateSchema(color="Blue"), user)
    assert account.color == "Blue"
    assert account.name == "Test Account"
    result = await service.delete(user, identifier)
    assert result.message == f"Delete Account {identifier} successfully"
    assert await service.list_all(None, user) == []


async def test_normalized_conflicts_and_self_rename(service, user):
    first = await service.create(user, _create_payload("Principal"))
    first_id = first.id
    second = await service.create(user, _create_payload("Poupança"))
    second_id = second.id
    with pytest.raises(HTTPException) as duplicate:
        await service.create(user, _create_payload("Principal"))
    assert duplicate.value.status_code == 409
    await service.update(first_id, AccountUpdateSchema(name="Principal"), user)
    with pytest.raises(HTTPException) as rename:
        await service.update(second_id, AccountUpdateSchema(name="Principal"), user)
    assert rename.value.status_code == 409
    assert (
        await service.find_by(user=user, filters={"id": second_id})
    ).name == "Poupança"


async def test_duplicate_name_rows_yield_409_not_multiple_results(
    service, user, account_session
):
    # Corrida: duas contas com o mesmo nome já persistem (sem constraint única).
    account_session.add_all(
        [
            _account_entity(user.id, "Dup"),
            _account_entity(user.id, "Dup"),
        ]
    )
    await account_session.commit()

    with pytest.raises(HTTPException) as duplicate:
        await service.create(user, _create_payload("Dup"))
    assert duplicate.value.status_code == 409


async def test_ownership_applies_to_queries_mutations_and_uniqueness(service, user):
    other = SimpleNamespace(id=uuid4(), username="other")
    own = await service.create(user, _create_payload("Same"))
    own_id = own.id
    foreign = await service.create(other, _create_payload("Same"))
    foreign_id = foreign.id
    assert len(await service.list_all(None, user)) == 1
    for operation in ("find", "update", "delete"):
        with pytest.raises(HTTPException) as error:
            if operation == "find":
                await service.find_by(user=user, filters={"id": foreign_id})
            elif operation == "update":
                await service.update(foreign_id, AccountUpdateSchema(name="No"), user)
            else:
                await service.delete(user, foreign_id)
        assert error.value.status_code == 404
    assert (await service.find_by(user=user, filters={"id": own_id})).name == "Same"
    assert (
        await service.find_by(user=other, filters={"id": foreign_id})
    ).name == "Same"


async def test_optional_lookup_and_list_do_not_hide_database_errors(service, user):
    assert (
        await service.find_by(user=user, filters={"id": uuid4()}, required=False)
        is None
    )
    for method in ("find_by", "list_all"):
        with patch.object(
            service.repository, method, side_effect=RuntimeError("database")
        ):
            with pytest.raises(HTTPException) as caught:
                if method == "find_by":
                    await service.find_by(
                        user=user, filters={"id": uuid4()}, required=False
                    )
                else:
                    await service.list_all(None, user)
        assert caught.value.status_code == 500


async def test_cached_reads_and_post_commit_invalidation(service, user, account_cache):
    account = await service.create(user, _create_payload("Original"))
    identifier = account.id
    filters = FilterPage(clean_cache=True)
    page = await service.list_all_cached(filters, user)
    assert isinstance(page[0], AccountSchema)
    assert filters.clean_cache is True
    with patch.object(
        service.repository, "list_all", side_effect=AssertionError("cache miss")
    ):
        assert await service.list_all_cached(None, user) == page
    await service.find_one_cached(user=user, filters={"name": "Original"})
    await service.update(identifier, AccountUpdateSchema(name="Renamed"), user)
    assert account_cache._data == {}
    assert (
        await service.find_one_cached(user=user, filters={"id": identifier})
    ).name == "Renamed"
    await service.delete(user, identifier)
    assert account_cache._data == {}


async def test_cache_failure_does_not_undo_committed_update(
    service, user, account_cache
):
    account = await service.create(user, _create_payload("Before"))
    identifier = account.id
    with (
        patch.object(
            account_cache,
            "scan_iter",
            side_effect=RuntimeError("cache unavailable"),
        ),
        patch.object(service.logger_params.logger, "warning") as warning,
    ):
        result = await service.update(
            identifier, AccountUpdateSchema(name="After"), user
        )
    assert isinstance(result, Message)
    warning.assert_called_once()
    assert (
        await service.find_by(user=user, filters={"id": identifier})
    ).name == "After"


async def test_find_by_name_used_for_uniqueness(service, user):
    with patch.object(
        service.repository, "find_by_name", wraps=service.repository.find_by_name
    ) as find_by_name:
        await service.create(user, _create_payload("Unique"))
    find_by_name.assert_awaited_once_with(user_id=user.id, name="Unique")


def _valid_data(name: str = "Principal") -> dict[str, object]:
    return {
        "name": name,
        "type": AccountTypeEnum.CASH,
        "is_active": True,
    }


async def test_build_entity_rejects_non_string_name(service, user):
    with pytest.raises(ValueError, match="name and type"):
        service._build_entity(user.id, {**_valid_data(), "name": 123})


async def test_build_entity_rejects_missing_type(service, user):
    data = _valid_data()
    data.pop("type")
    with pytest.raises(ValueError, match="name and type"):
        service._build_entity(user.id, data)


async def test_build_entity_rejects_non_bool_is_active(service, user):
    with pytest.raises(ValueError, match="is_active"):
        service._build_entity(user.id, {**_valid_data(), "is_active": 1})


async def test_normalize_rejects_non_string_name(service, user):
    with pytest.raises(ValueError, match="name must be a string"):
        await service._normalize({"name": 123}, user)
