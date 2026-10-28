from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.core.exceptions import handle_service_exception
from app.models import utcnow
from app.shared.schemas import FilterPage, Message
from app.shared.utils.string import to_snake_case
from app.temp import BaseService
from tests.app.temp.conftest import (
    Item,
    ItemCreate,
    ItemRepository,
    ItemSchema,
    ItemService,
    ItemUpdate,
)

pytestmark = pytest.mark.asyncio


async def test_inherited_factory_builds_configured_repository(
    session, logging_params, user
):
    class ConfiguredService(ItemService):
        repository_class = ItemRepository

    service = ConfiguredService.from_session(
        session, alias="Item", logger_params=logging_params
    )
    assert isinstance(service, ConfiguredService)
    assert isinstance(service.repository, ItemRepository)
    assert service.repository.session is session
    entity = await service.create(user, ItemCreate(name="From session"))
    assert await service.find_by(user=user, filters={"id": entity.id}) is entity


async def test_factory_requires_explicit_repository_class(session):
    with pytest.raises(TypeError, match="ItemService must declare repository_class"):
        ItemService.from_session(session)


async def test_inherited_crud_cycle(service, user):
    entity = await service.create(user, ItemCreate(name="Original", description="old"))
    assert entity.user_id == user.id
    assert await service.find_by(user=user, filters={"id": entity.id}) is entity
    assert await service.list_all(FilterPage(), user) == [entity]
    result = await service.update(entity.id, ItemUpdate(description=None), user)
    assert isinstance(result, Message)
    assert entity.name == "Original"
    assert entity.description is None
    assert isinstance(await service.delete(user, entity.id), Message)
    assert await service.list_all(None, user) == []


@pytest.mark.parametrize("operation", ["find", "update", "delete"])
async def test_foreign_missing_and_deleted_entities_are_not_accessible(
    service, records, user, operation
):
    for identifier in [records[2].id, uuid4()]:
        with pytest.raises(HTTPException) as caught:
            if operation == "find":
                await service.find_by(user=user, filters={"id": identifier})
            elif operation == "update":
                await service.update(identifier, ItemUpdate(name="No"), user)
            else:
                await service.delete(user, identifier)
        assert caught.value.status_code == 404
    assert len((await service.repository.session.scalars(select(Item))).all()) == 3


async def test_optional_lookup_returns_none_only_for_real_absence(service, user):
    assert (
        await service.find_by(user=user, filters={"id": uuid4()}, required=False)
        is None
    )
    with patch.object(service.repository, "find_by", side_effect=RuntimeError("db")):
        with pytest.raises(HTTPException) as caught:
            await service.find_by(user=user, filters={"id": uuid4()}, required=False)
    assert caught.value.status_code == 500


@pytest.mark.parametrize("fail", [False, True])
async def test_specialized_operation_uses_context_once(service, user, fail):
    target = uuid4()
    with (
        patch("app.temp.service.log_service_success") as success,
        patch(
            "app.temp.service.handle_service_exception", wraps=handle_service_exception
        ) as error,
    ):
        if fail:
            with pytest.raises(HTTPException):
                await service.specialized(user, target, fail=True)
            error.assert_called_once()
            success.assert_not_called()
            call = error.call_args
        else:
            assert await service.specialized(user, target) == "done"
            success.assert_called_once()
            error.assert_not_called()
            call = success.call_args
        assert call.kwargs["operation"] == "specialized"
        assert call.kwargs["user_request"] == user.username
        assert call.kwargs["logger"].extra["target_id"] == str(target)


@pytest.mark.parametrize(
    "field", ["user_id", "id", "created_at", "deleted_at", "updated_at"]
)
@pytest.mark.parametrize("operation", ["create", "update"])
async def test_client_managed_fields_rejected(service, records, user, field, operation):
    class UnsafePayload(BaseModel):
        model_config = {"extra": "allow"}

    payload = UnsafePayload.model_validate({field: str(uuid4())})
    identifier = records[0].id
    with pytest.raises(HTTPException) as caught:
        if operation == "create":
            await service.create(user, payload)
        else:
            await service.update(identifier, payload, user)
    assert caught.value.status_code == 422


async def test_constructed_entity_must_have_trusted_owner(service, user):
    with (
        patch.object(
            service, "_build_entity", return_value=Item(user_id=uuid4(), name="No")
        ),
        pytest.raises(HTTPException) as caught,
    ):
        await service.create(user, ItemCreate(name="No"))
    assert caught.value.status_code == 500
    assert await service.list_all(None, user) == []


@pytest.mark.parametrize(
    "failure",
    ["list_all", "find_by", "_prepare_create", "save", "update", "delete", "commit"],
)
async def test_failures_translate_once_without_false_success(
    service, records, user, failure
):
    identifier = records[0].id
    if failure == "_prepare_create":
        target = service
    elif failure == "commit":
        target = service.repository.session
    else:
        target = service.repository
    with (
        patch.object(
            target, failure, new=AsyncMock(side_effect=RuntimeError("failure"))
        ),
        patch("app.temp.service.log_service_success") as success,
        patch(
            "app.temp.service.handle_service_exception", wraps=handle_service_exception
        ) as error,
        pytest.raises(HTTPException) as caught,
    ):
        if failure == "list_all":
            await service.list_all(None, user)
        elif failure == "find_by":
            await service.find_by(user=user, filters={"id": identifier})
        elif failure in ("_prepare_create", "save"):
            await service.create(user, ItemCreate(name="No"))
        elif failure == "delete":
            await service.delete(user, identifier)
        else:
            await service.update(identifier, ItemUpdate(name="No"), user)
    assert caught.value.status_code == 500
    error.assert_called_once()
    success.assert_not_called()
    assert error.call_args.kwargs["user_request"] == user.username
    assert await service.find_by(user=user, filters={"id": identifier}) is not None


async def test_lookup_metadata_does_not_reach_repository(service, records, user):
    with patch.object(
        service.repository, "find_by", wraps=service.repository.find_by
    ) as find:
        await service.find_by(user=user, filters={"id": records[0].id}, required=False)
    find.assert_awaited_once_with(user_id=user.id, filters={"id": records[0].id})


async def test_success_only_after_commit(service, user):
    events = []
    session = service.repository.session
    original_commit = session.commit

    async def commit():
        events.append("commit")
        await original_commit()

    with (
        patch.object(session, "commit", side_effect=commit),
        patch(
            "app.temp.service.log_service_success",
            side_effect=lambda *a, **kw: events.append("success"),
        ),
    ):
        await service.create(user, ItemCreate(name="Name"))
    assert events == ["commit", "success"]


class NormalizedItemService(ItemService):
    async def _normalize(self, data, user, entity_id=None):
        if "name" in data:
            data["name_code"] = to_snake_case(data["name"])
            duplicate = await self.repository.find_by(
                user_id=user.id, filters={"name_code": data["name_code"]}
            )
            if duplicate is not None and (
                entity_id is None or duplicate.id != entity_id
            ):
                raise HTTPException(status_code=409, detail="Item already exists")
        return data


async def test_normalized_extension_uses_inherited_flows(
    repository, logging_params, user
):
    service = NormalizedItemService(
        repository, alias="Item", logger_params=logging_params
    )
    entity = await service.create(user, ItemCreate(name="  Electric Company  "))
    identifier = entity.id
    assert entity.name_code == "electric_company"
    with pytest.raises(HTTPException) as duplicate:
        await service.create(user, ItemCreate(name="Electric Company"))
    assert duplicate.value.status_code == 409
    await service.update(identifier, ItemUpdate(name="Electric Company"), user)
    await service.update(identifier, ItemUpdate(name="New Company"), user)
    entity = await service.find_by(user=user, filters={"id": identifier})
    assert entity.name_code == "new_company"
    await service.update(identifier, ItemUpdate(description="No name change"), user)
    entity = await service.find_by(user=user, filters={"id": identifier})
    assert entity.name == "New Company"
    assert entity.name_code == "new_company"
    assert entity.description == "No name change"
    second = await service.create(user, ItemCreate(name="Other"))
    second_id = second.id
    with pytest.raises(HTTPException) as rename:
        await service.update(second_id, ItemUpdate(name="New Company"), user)
    assert rename.value.status_code == 409
    other = type(user)(id=uuid4(), username="other")
    different_owner = await service.create(other, ItemCreate(name="New Company"))
    assert different_owner.user_id == other.id
    assert different_owner.name_code == "new_company"
    original_second = await service.find_by(user=user, filters={"id": second_id})
    assert original_second.name == "Other"


class LogicalItemRepository(ItemRepository):
    def _visibility(self):
        return (Item.deleted_at.is_(None),)

    async def _delete(self, entity):
        entity.deleted_at = utcnow()


async def test_logical_deletion_extension_keeps_row_and_hides_it(
    session, logging_params, user
):
    service = ItemService(
        LogicalItemRepository(session), alias="Item", logger_params=logging_params
    )
    entity = await service.create(user, ItemCreate(name="Logical"))
    identifier = entity.id
    await service.delete(user, identifier)
    assert await service.list_all(None, user) == []
    assert (
        await service.find_by(user=user, filters={"id": identifier}, required=False)
        is None
    )
    stored = await session.get(Item, identifier)
    await session.refresh(stored)
    assert stored.deleted_at is not None
    deleted_at = stored.deleted_at
    with pytest.raises(HTTPException) as repeated:
        await service.delete(user, identifier)
    assert repeated.value.status_code == 404
    assert (await session.get(Item, identifier)).deleted_at == deleted_at


async def test_service_rejects_invalid_cache_namespace(repository, logging_params):
    with pytest.raises(ValueError, match="Cache namespaces"):
        ItemService(
            repository,
            alias="Item",
            logger_params=logging_params,
            schema_class=ItemSchema,
            cache_prefix="Invalid Prefix",
        )


async def test_service_rejects_non_positive_ttl(repository, logging_params):
    with pytest.raises(ValueError, match="Cache TTL"):
        ItemService(
            repository,
            alias="Item",
            logger_params=logging_params,
            schema_class=ItemSchema,
            cache_prefix="items",
            default_ttl=0,
        )


async def test_cached_list_rejects_unexpected_envelope(
    cached_service, user, cache_redis
):
    cache = AsyncMock()
    cache.get_list.return_value = "bogus"
    with (
        patch.object(cached_service, "_cache", return_value=cache),
        pytest.raises(HTTPException) as caught,
    ):
        await cached_service.list_all_cached(None, user)
    assert caught.value.status_code == 500


async def test_base_build_entity_is_abstract():
    with pytest.raises(NotImplementedError):
        BaseService._build_entity(None, None, None)


class TranslatingService(ItemService):
    def _translate_exception(self, exception):
        if isinstance(exception, ValueError):
            return HTTPException(status_code=409, detail="translated")
        return exception


async def test_translation_hook_rewrites_exception_before_handling(service, user):
    translating = TranslatingService(
        service.repository,
        alias="Item",
        logger_params=service.logger_params,
    )
    with (
        patch.object(
            translating.repository,
            "save",
            side_effect=ValueError("conflict"),
        ),
        patch(
            "app.temp.service.handle_service_exception",
            wraps=handle_service_exception,
        ) as handler,
        pytest.raises(HTTPException) as caught,
    ):
        await translating.create(user, ItemCreate(name="No"))
    assert caught.value.status_code == 409
    assert caught.value.detail == "translated"
    handler.assert_called_once()
    assert handler.call_args.args[0].detail == "translated"
    assert handler.call_args.kwargs["operation"] == "create"


async def test_translation_hook_passthrough_for_untranslated_errors(service, user):
    translating = TranslatingService(
        service.repository,
        alias="Item",
        logger_params=service.logger_params,
    )
    with (
        patch.object(
            translating.repository,
            "save",
            side_effect=RuntimeError("database"),
        ),
        pytest.raises(HTTPException) as caught,
    ):
        await translating.create(user, ItemCreate(name="No"))
    assert caught.value.status_code == 500
