from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError

from app.domain.receipt.receipt_interpretation_profile.schema import (
    ReceiptInterpretationProfileCreateSchema as Create,
    ReceiptInterpretationProfileFilter as Filter,
    ReceiptInterpretationProfileUpdateSchema as Update,
)
from app.domain.receipt.receipt_interpretation_profile.service import (
    ReceiptInterpretationProfileService as Service,
)
from app.models import ReceiptFieldRule, ReceiptInterpretationProfile
from tests.app.domain.receipt.receipt_interpretation_profile.test_schema import (
    field_payload,
)

MODULE = "app.domain.receipt.receipt_interpretation_profile.service"


@pytest.fixture
def repository():
    repo = SimpleNamespace(
        find_by=AsyncMock(),
        find_by_code=AsyncMock(return_value=None),
        list_all=AsyncMock(return_value=[]),
        save=AsyncMock(),
        delete=AsyncMock(),
        committed=False,
    )

    @asynccontextmanager
    async def transaction():
        yield
        repo.committed = True

    repo.transaction = transaction
    return repo


@pytest.mark.asyncio
async def test_success_is_logged_only_after_commit_without_configuration(
    repository, user
):
    service = Service(repository)
    payload = Create(
        name="Nubank",
        institution_code="NUBANK",
        field_rules=[field_payload()],
    )
    with patch(f"{MODULE}.log_service_success") as success:
        success.side_effect = lambda *args, **kwargs: (
            None if repository.committed else pytest.fail("Logged before commit")
        )
        result = await service.create(user, payload)
    assert result.scope == "private"
    entity = repository.save.await_args.args[0]
    assert entity.user_id == user.id
    assert entity.field_rules[0].configuration == payload.field_rules[
        0
    ].configuration.model_dump(mode="json")
    assert str(entity.id) in success.call_args.kwargs["message"]
    assert "patterns" not in str(success.call_args)
    assert "paid_amount" not in str(success.call_args)


@pytest.mark.asyncio
async def test_commit_failure_uses_captured_user_metadata(repository):
    state = {"expired": False}

    class ExpiringUser:
        @property
        def id(self):
            assert not state["expired"], "Read expired owner"
            return owner_id

        @property
        def username(self):
            assert not state["expired"], "Read expired username"
            return "owner"

    owner_id = uuid4()

    @asynccontextmanager
    async def failed_transaction():
        yield
        state["expired"] = True
        raise RuntimeError("commit failure")

    repository.transaction = failed_transaction
    with patch(f"{MODULE}.log_service_success") as success:
        with pytest.raises(HTTPException) as caught:
            await Service(repository).create(
                ExpiringUser(), Create(name="NU", institution_code="NU")
            )
    assert caught.value.status_code == 500
    assert isinstance(caught.value.__cause__, RuntimeError)
    success.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["find_by", "update", "delete"])
async def test_not_found_and_general_write_permissions(repository, user, operation):
    service = Service(repository)

    async def execute():
        if operation == "update":
            return await service.update(uuid4(), Update(), user)
        return await getattr(service, operation)(uuid4(), user)

    repository.find_by.return_value = None
    with pytest.raises(HTTPException) as caught:
        await execute()
    assert caught.value.status_code == 404
    general = ReceiptInterpretationProfile(
        user_id=None, name="Geral", institution_code=None
    )
    repository.find_by.return_value = general
    if operation == "find_by":
        assert (await execute()).scope == "system"
    else:
        with pytest.raises(HTTPException) as caught:
            await execute()
        assert caught.value.status_code == 403
    repository.save.assert_not_awaited()
    repository.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_both_collections_validated_before_any_mutation(repository, user):
    entity = ReceiptInterpretationProfile(
        user_id=user.id, name="NU", institution_code="NU"
    )
    repository.find_by.return_value = entity
    payload = Update(
        name="Changed",
        field_rules=[field_payload()],
        identification_rules=[{"id": uuid4(), "pattern": "NU", "weight": 1}],
    )
    with pytest.raises(HTTPException) as caught:
        await Service(repository).update(entity.id, payload, user)
    assert caught.value.status_code == 422
    assert entity.name == "NU"
    repository.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_inactive_field_rules_return_422(repository, user):
    entity = ReceiptInterpretationProfile(
        user_id=user.id, name="NU", institution_code="NU"
    )
    repository.find_by.return_value = entity
    with pytest.raises(HTTPException) as caught:
        await Service(repository).update(
            entity.id,
            Update(
                field_rules=[field_payload(), field_payload() | {"is_active": False}]
            ),
            user,
        )
    assert caught.value.status_code == 422
    repository.save.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation", ["create", "list_all", "find_by", "update", "delete"]
)
async def test_infrastructure_failure_is_not_empty_or_success(
    repository, user, operation
):
    failure = OperationalError("SELECT", {}, RuntimeError("database unavailable"))
    repository.find_by.side_effect = failure
    repository.find_by_code.side_effect = failure
    repository.list_all.side_effect = failure
    service = Service(repository)
    with patch(f"{MODULE}.log_service_success") as success:
        with pytest.raises(HTTPException) as caught:
            if operation == "create":
                await service.create(user, Create(name="NU", institution_code="NU"))
            elif operation == "list_all":
                await service.list_all(Filter(), user)
            elif operation == "update":
                await service.update(uuid4(), Update(), user)
            else:
                await getattr(service, operation)(uuid4(), user)
    assert caught.value.status_code == 500
    assert caught.value.__cause__ is failure
    success.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_persisted_configuration_fails_explicitly(repository, user):
    entity = ReceiptInterpretationProfile(
        user_id=user.id, name="NU", institution_code="NU"
    )
    entity.field_rules.append(
        ReceiptFieldRule(
            profile_id=entity.id,
            field_name="paid_amount",
            configuration={"legacy": "invalid"},
        )
    )
    repository.find_by.return_value = entity
    with patch(f"{MODULE}.log_service_success") as success:
        with pytest.raises(HTTPException) as caught:
            await Service(repository).find_by(entity.id, user)
    assert caught.value.status_code == 500
    success.assert_not_called()


def test_translate_only_known_constraint_across_wrappers():
    diagnostic = SimpleNamespace(
        diag=SimpleNamespace(
            constraint_name="uq_receipt_profiles_owner_institution_live"
        )
    )
    wrapper = Mock(
        __cause__=diagnostic, __context__=None, diag=None, constraint_name=None
    )
    conflict = Service._translate_error(IntegrityError("INSERT", {}, wrapper))
    assert conflict.status_code == 409
    unknown = IntegrityError("INSERT", {}, RuntimeError("other constraint"))
    assert Service._translate_error(unknown) is unknown
