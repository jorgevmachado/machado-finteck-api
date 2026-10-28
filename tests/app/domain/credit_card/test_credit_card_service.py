from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
import pytest

from app.domain.credit_card.repository import CreditCardRepository
from app.domain.credit_card.schema import (
    CreditCardCreateSchema,
    CreditCardSchema,
    CreditCardUpdateSchema,
)
from app.domain.credit_card.service import CreditCardService
from app.models import CreditCard, CreditCardBrandEnum
from app.shared.schemas import FilterPage, Message
from app.temp import BaseService

pytestmark = pytest.mark.asyncio


def _create_payload(name: str, **overrides) -> CreditCardCreateSchema:
    return CreditCardCreateSchema(
        name=name,
        brand=CreditCardBrandEnum.VISA,
        closing_day=15,
        due_day=25,
        **overrides,
    )


async def test_credit_card_inherits_crud_without_redefining_it(
    service, credit_card_session
):
    assert isinstance(service.repository, CreditCardRepository)
    assert service.repository.session is credit_card_session
    for method in ("list_all", "find_by", "create", "update", "delete"):
        assert getattr(CreditCardService, method) is getattr(BaseService, method)


async def test_crud_preserves_partial_update_and_deletes(
    service, user, create_credit_card_payload, update_credit_card_payload
):
    credit_card = await service.create(user, create_credit_card_payload)
    identifier = str(credit_card.id)
    assert credit_card.user_id == user.id
    assert credit_card.name == "Test Credit Card"
    assert credit_card.brand == CreditCardBrandEnum.VISA
    assert await service.find_by(user=user, filters={"id": identifier}) is credit_card
    assert await service.list_all(FilterPage(), user) == [credit_card]
    result = await service.update(identifier, update_credit_card_payload, user)
    assert isinstance(result, Message)
    assert result.message == f"Update CreditCard {identifier} successfully"
    assert credit_card.name == "Test Credit Card"
    await service.update(identifier, CreditCardUpdateSchema(color="Blue"), user)
    assert credit_card.color == "Blue"
    assert credit_card.name == "Test Credit Card"
    result = await service.delete(user, identifier)
    assert result.message == f"Delete CreditCard {identifier} successfully"
    assert await service.list_all(None, user) == []


async def test_normalized_conflicts_and_self_rename(service, user):
    first = await service.create(user, _create_payload("Visa"))
    first_id = first.id
    second = await service.create(user, _create_payload("Master"))
    second_id = second.id
    with pytest.raises(HTTPException) as duplicate:
        await service.create(user, _create_payload("Visa"))
    assert duplicate.value.status_code == 409
    await service.update(first_id, CreditCardUpdateSchema(name="Visa"), user)
    with pytest.raises(HTTPException) as rename:
        await service.update(second_id, CreditCardUpdateSchema(name="Visa"), user)
    assert rename.value.status_code == 409
    assert (
        await service.find_by(user=user, filters={"id": second_id})
    ).name == "Master"


async def test_duplicate_name_rows_yield_409_not_multiple_results(
    service, user, credit_card_session
):
    # Corrida: dois cartões com o mesmo nome já persistem (sem constraint única).
    credit_card_session.add_all(
        [
            CreditCard(
                user_id=user.id,
                name="Dup",
                brand=CreditCardBrandEnum.VISA,
                is_active=True,
                closing_day=15,
                due_day=25,
                description=None,
                last_four_digits=None,
                limit=None,
                color=None,
                icon=None,
            ),
            CreditCard(
                user_id=user.id,
                name="Dup",
                brand=CreditCardBrandEnum.MASTERCARD,
                is_active=True,
                closing_day=10,
                due_day=20,
                description=None,
                last_four_digits=None,
                limit=None,
                color=None,
                icon=None,
            ),
        ]
    )
    await credit_card_session.commit()

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
                await service.update(
                    foreign_id, CreditCardUpdateSchema(name="No"), user
                )
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


async def test_credit_card_cached_reads_and_post_commit_invalidation(
    service, user, credit_card_cache
):
    credit_card = await service.create(user, _create_payload("Original"))
    identifier = credit_card.id
    filters = FilterPage(clean_cache=True)
    page = await service.list_all_cached(filters, user)
    assert isinstance(page[0], CreditCardSchema)
    assert filters.clean_cache is True
    with patch.object(
        service.repository, "list_all", side_effect=AssertionError("cache miss")
    ):
        assert await service.list_all_cached(None, user) == page
    await service.find_one_cached(user=user, filters={"name": "Original"})
    await service.update(identifier, CreditCardUpdateSchema(name="Renamed"), user)
    assert credit_card_cache._data == {}
    assert (
        await service.find_one_cached(user=user, filters={"id": identifier})
    ).name == "Renamed"
    await service.delete(user, identifier)
    assert credit_card_cache._data == {}


async def test_cache_failure_does_not_undo_committed_update(
    service, user, credit_card_cache
):
    credit_card = await service.create(user, _create_payload("Before"))
    identifier = credit_card.id
    with (
        patch.object(
            credit_card_cache,
            "scan_iter",
            side_effect=RuntimeError("cache unavailable"),
        ),
        patch.object(service.logger_params.logger, "warning") as warning,
    ):
        result = await service.update(
            identifier, CreditCardUpdateSchema(name="After"), user
        )
    assert isinstance(result, Message)
    warning.assert_called_once()
    assert (
        await service.find_by(user=user, filters={"id": identifier})
    ).name == "After"


def _valid_data(name: str = "Visa") -> dict[str, object]:
    return {
        "name": name,
        "brand": CreditCardBrandEnum.VISA,
        "closing_day": 15,
        "due_day": 25,
        "is_active": True,
    }


async def test_build_entity_rejects_non_string_name(service, user):
    with pytest.raises(ValueError, match="name and brand"):
        service._build_entity(user.id, {**_valid_data(), "name": 123})


async def test_build_entity_rejects_missing_brand(service, user):
    data = _valid_data()
    data.pop("brand")
    with pytest.raises(ValueError, match="name and brand"):
        service._build_entity(user.id, data)


async def test_build_entity_rejects_invalid_closing_or_due_day(service, user):
    with pytest.raises(ValueError, match="closing_day and due_day"):
        service._build_entity(user.id, {**_valid_data(), "closing_day": "15"})


async def test_build_entity_rejects_non_bool_is_active(service, user):
    with pytest.raises(ValueError, match="is_active"):
        service._build_entity(user.id, {**_valid_data(), "is_active": 1})


async def test_normalize_rejects_non_string_name(service, user):
    with pytest.raises(ValueError, match="name must be a string"):
        await service._normalize({"name": 123}, user)
