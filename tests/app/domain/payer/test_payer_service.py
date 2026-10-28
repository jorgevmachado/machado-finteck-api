from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import func, select

from app.core.exceptions import handle_service_exception
from app.domain.payer.repository import PayerRepository
from app.domain.payer.schema import PayerCreateSchema, PayerSchema, PayerUpdateSchema
from app.domain.payer.service import PayerService
from app.models import Payer
from app.shared.schemas import FilterPage, Message
from app.temp import BaseService

pytestmark = pytest.mark.asyncio


async def test_payer_inherits_crud_without_redefining_it(service, payer_session):
    assert isinstance(service.repository, PayerRepository)
    assert service.repository.session is payer_session
    for method in ("list_all", "find_by", "create", "update", "delete"):
        assert getattr(PayerService, method) is getattr(BaseService, method)


async def test_crud_normalizes_names_preserves_partial_update_and_deletes(
    service, user, create_payer_payload, update_payer_payload
):
    payer = await service.create(user, create_payer_payload)
    identifier = str(payer.id)
    assert payer.user_id == user.id
    assert payer.name_code == "electric_company"
    assert await service.find_by(user=user, filters={"id": identifier}) is payer
    assert await service.list_all(FilterPage(), user) == [payer]
    result = await service.update(identifier, update_payer_payload, user)
    assert isinstance(result, Message)
    assert result.message == f"Update Payer {identifier} successfully"
    assert payer.name == "Water Company"
    assert payer.name_code == "water_company"
    await service.update(identifier, PayerUpdateSchema(), user)
    assert payer.name == "Water Company"
    result = await service.delete(user, identifier)
    assert result.message == f"Delete Payer {identifier} successfully"
    assert await service.list_all(None, user) == []


async def test_normalized_conflicts_and_self_rename(service, user):
    first = await service.create(user, PayerCreateSchema(name="Electric Company"))
    first_id = first.id
    second = await service.create(user, PayerCreateSchema(name="Water Company"))
    second_id = second.id
    with pytest.raises(HTTPException) as duplicate:
        await service.create(user, PayerCreateSchema(name=" electric company "))
    assert duplicate.value.status_code == 409
    await service.update(first_id, PayerUpdateSchema(name="electric company"), user)
    with pytest.raises(HTTPException) as rename:
        await service.update(
            second_id, PayerUpdateSchema(name="Electric Company"), user
        )
    assert rename.value.status_code == 409
    assert (
        await service.find_by(user=user, filters={"id": second_id})
    ).name == "Water Company"


async def test_ownership_applies_to_queries_mutations_and_uniqueness(service, user):
    other = SimpleNamespace(id=uuid4(), username="other")
    own = await service.create(user, PayerCreateSchema(name="Same"))
    own_id = own.id
    foreign = await service.create(other, PayerCreateSchema(name="Same"))
    foreign_id = foreign.id
    assert len(await service.list_all(None, user)) == 1
    for operation in ("find", "update", "delete"):
        with pytest.raises(HTTPException) as error:
            if operation == "find":
                await service.find_by(user=user, filters={"id": foreign_id})
            elif operation == "update":
                await service.update(foreign_id, PayerUpdateSchema(name="No"), user)
            else:
                await service.delete(user, foreign_id)
        assert error.value.status_code == 404
    assert (await service.find_by(user=user, filters={"id": own_id})).name == "Same"
    assert (
        await service.find_by(user=other, filters={"id": foreign_id})
    ).name == "Same"


async def test_resolve_reuses_owner_record_or_creates_once(
    service, user, payer_session
):
    with patch("app.temp.service.log_service_success") as success:
        first = await service.resolve(user, "  Electric Company  ")
        second = await service.resolve(user, "electric company")
    assert first.id == second.id
    assert first.name == "Electric Company"
    assert await payer_session.scalar(select(func.count()).select_from(Payer)) == 1
    assert [call.kwargs["operation"] for call in success.call_args_list] == [
        "resolve",
        "resolve",
    ]


@pytest.mark.parametrize("failure", ["find_by", "save", "commit"])
async def test_resolve_translates_once_and_rolls_back(service, user, failure):
    target = service.repository.session if failure == "commit" else service.repository
    with (
        patch.object(
            target, failure, new=AsyncMock(side_effect=RuntimeError("database failure"))
        ),
        patch(
            "app.temp.service.handle_service_exception", wraps=handle_service_exception
        ) as error,
        patch("app.temp.service.log_service_success") as success,
        pytest.raises(HTTPException) as caught,
    ):
        await service.resolve(user, "New")
    assert caught.value.status_code == 500
    error.assert_called_once()
    assert error.call_args.kwargs["operation"] == "resolve"
    assert error.call_args.kwargs["user_request"] == user.username
    success.assert_not_called()
    assert await service.list_all(None, user) == []


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


async def test_payer_cached_reads_and_post_commit_invalidation(
    service, user, payer_cache
):
    payer = await service.create(user, PayerCreateSchema(name="Original"))
    identifier = payer.id
    filters = FilterPage(clean_cache=True)
    page = await service.list_all_cached(filters, user)
    assert isinstance(page[0], PayerSchema)
    assert filters.clean_cache is True
    with patch.object(
        service.repository, "list_all", side_effect=AssertionError("cache miss")
    ):
        assert await service.list_all_cached(None, user) == page
    await service.find_one_cached(user=user, filters={"name_code": "original"})
    await service.update(identifier, PayerUpdateSchema(name="Renamed"), user)
    assert payer_cache._data == {}
    assert (
        await service.find_one_cached(user=user, filters={"id": identifier})
    ).name == "Renamed"
    await service.delete(user, identifier)
    assert payer_cache._data == {}


async def test_cache_failure_does_not_undo_committed_update(service, user, payer_cache):
    payer = await service.create(user, PayerCreateSchema(name="Before"))
    identifier = payer.id
    with (
        patch.object(
            payer_cache, "scan_iter", side_effect=RuntimeError("cache unavailable")
        ),
        patch.object(service.logger_params.logger, "warning") as warning,
    ):
        result = await service.update(identifier, PayerUpdateSchema(name="After"), user)
    assert isinstance(result, Message)
    warning.assert_called_once()
    assert (
        await service.find_by(user=user, filters={"id": identifier})
    ).name == "After"


async def test_build_entity_rejects_non_string_name(service, user):
    with pytest.raises(ValueError, match="normalized name and name_code"):
        service._build_entity(user.id, {"name": 123, "name_code": "x"})


async def test_build_entity_rejects_non_string_name_code(service, user):
    with pytest.raises(ValueError, match="normalized name and name_code"):
        service._build_entity(user.id, {"name": "X", "name_code": None})


async def test_normalize_rejects_non_string_name(service, user):
    with pytest.raises(ValueError, match="name must be a string"):
        await service._normalize({"name": 123}, user)
