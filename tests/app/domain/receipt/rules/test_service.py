from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi_pagination import LimitOffsetParams
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.pagination import CustomLimitOffsetPage
from app.domain.receipt.rules.schema import (
    ReceiptRulesCreateSchema,
    ReceiptRulesFilter,
    ReceiptRulesUpdateSchema,
)
from app.domain.receipt.rules.service import ReceiptRulesService

pytestmark = pytest.mark.asyncio
MODULE = "app.domain.receipt.rules.service"


async def test_create_owns_nested_aggregate_and_logs_only_after_commit(
    rules_repository, user, rule_payload
):
    service = ReceiptRulesService(rules_repository)
    payload = ReceiptRulesCreateSchema(
        name="Bank",
        institution_code="BANK",
        field_rules=[rule_payload],
        identification_rules=[{"pattern": "BANK", "weight": 2}],
    )
    with patch(f"{MODULE}.log_service_success") as success:
        success.side_effect = lambda *args, **kwargs: (
            None if rules_repository.committed else pytest.fail("Success before commit")
        )
        result = await service.create(user, payload)
    entity = rules_repository.save.await_args.args[0]
    assert entity.user_id == user.id
    assert result.id == entity.id and result.scope == "private"
    assert entity.field_rules[0].configuration["parser"] == "text"
    assert entity.identification_rules[0].profile_id == entity.id
    assert "patterns" not in str(success.call_args)


async def test_create_duplicate_returns_conflict_without_save(
    rules_repository, user, profile
):
    rules_repository.find_by_code.return_value = profile
    with pytest.raises(HTTPException) as caught:
        await ReceiptRulesService(rules_repository).create(
            user, ReceiptRulesCreateSchema(name="Other name", institution_code="BANK")
        )
    assert caught.value.status_code == 409
    rules_repository.save.assert_not_awaited()
    assert rules_repository.rolled_back


async def test_list_and_find_map_complete_aggregate_and_keep_pagination(
    rules_repository, user, profile
):
    service = ReceiptRulesService(rules_repository)
    rules_repository.list_all.return_value = [profile]
    filters = ReceiptRulesFilter()
    result = await service.list_all(filters, user)
    assert result[0].id == profile.id
    rules_repository.list_all.assert_awaited_with(filters, user_id=user.id)
    rules_repository.list_all.return_value = CustomLimitOffsetPage.create(
        [profile], params=LimitOffsetParams(limit=2, offset=0), total=5
    )
    page = await service.list_all(filters, user)
    assert page.meta.total == 5 and page.items[0].id == profile.id
    rules_repository.find_by.return_value = profile
    assert (await service.find_by(profile.id, user)).id == profile.id
    rules_repository.find_by.assert_awaited_with(id=profile.id, user_id=user.id)


@pytest.mark.parametrize("operation", ["find_by", "update", "delete"])
async def test_missing_or_foreign_profiles_return_404(
    rules_repository, user, operation
):
    service = ReceiptRulesService(rules_repository)
    with pytest.raises(HTTPException) as caught:
        if operation == "update":
            await service.update(uuid4(), ReceiptRulesUpdateSchema(), user)
        else:
            await getattr(service, operation)(uuid4(), user)
    assert caught.value.status_code == 404
    rules_repository.save.assert_not_awaited()
    rules_repository.delete.assert_not_awaited()


@pytest.mark.parametrize("operation", ["update", "delete"])
async def test_general_is_read_only(rules_repository, user, profile, operation):
    profile.user_id = None
    profile.institution_code = None
    rules_repository.find_by.return_value = profile
    service = ReceiptRulesService(rules_repository)
    assert (await service.find_by(profile.id, user)).scope == "system"
    with pytest.raises(HTTPException) as caught:
        if operation == "update":
            await service.update(
                profile.id, ReceiptRulesUpdateSchema(name="Changed"), user
            )
        else:
            await service.delete(profile.id, user)
    assert caught.value.status_code == 403
    rules_repository.save.assert_not_awaited()
    rules_repository.delete.assert_not_awaited()


async def test_update_omission_empty_and_mixed_collections(
    rules_repository, user, profile, rule_payload
):
    service = ReceiptRulesService(rules_repository)
    rules_repository.find_by.return_value = profile
    await service.update(profile.id, ReceiptRulesUpdateSchema(name="Renamed"), user)
    rules_repository.find_by.assert_awaited_with(
        id=profile.id, user_id=user.id, for_update=True
    )
    assert profile.name == "Renamed"
    assert rules_repository.save.await_args.kwargs == {
        "fields": None,
        "identification": None,
    }
    first = profile.field_rules[0]
    payload = ReceiptRulesUpdateSchema(
        field_rules=[
            {"id": first.id, **rule_payload},
            {"field_name": "category", "configuration": {"strategy": "not_found"}},
        ],
        identification_rules=[],
    )
    await service.update(profile.id, payload, user)
    plans = rules_repository.save.await_args.kwargs
    assert plans["fields"].entries[0].id == first.id
    assert plans["fields"].entries[1].id is None
    assert plans["identification"].remove_ids == (profile.identification_rules[0].id,)


async def test_invalid_second_collection_never_changes_root_or_saves(
    rules_repository, user, profile, rule_payload
):
    rules_repository.find_by.return_value = profile
    payload = ReceiptRulesUpdateSchema(
        name="Should not change",
        field_rules=[rule_payload],
        identification_rules=[{"id": uuid4(), "pattern": "BANK", "weight": 1}],
    )
    with pytest.raises(HTTPException) as caught:
        await ReceiptRulesService(rules_repository).update(profile.id, payload, user)
    assert caught.value.status_code == 422
    assert profile.name == "Banco"
    rules_repository.save.assert_not_awaited()


async def test_duplicate_final_fields_rejected_before_save(
    rules_repository, user, profile, rule_payload
):
    rules_repository.find_by.return_value = profile
    with pytest.raises(HTTPException) as caught:
        await ReceiptRulesService(rules_repository).update(
            profile.id,
            ReceiptRulesUpdateSchema(field_rules=[rule_payload, rule_payload]),
            user,
        )
    assert caught.value.status_code == 422
    rules_repository.save.assert_not_awaited()


async def test_delete_locks_then_delegates(rules_repository, user, profile):
    rules_repository.find_by.return_value = profile
    result = await ReceiptRulesService(rules_repository).delete(profile.id, user)
    rules_repository.find_by.assert_awaited_with(
        id=profile.id, user_id=user.id, for_update=True
    )
    rules_repository.delete.assert_awaited_once_with(profile)
    assert str(profile.id) in result.message and rules_repository.committed


@pytest.mark.parametrize(
    "operation", ["create", "find_by", "list_all", "update", "delete", "seed_defaults"]
)
async def test_infrastructure_errors_are_not_success_or_empty(
    rules_repository, user, operation
):
    failure = OperationalError("query", {}, RuntimeError("database unavailable"))
    rules_repository.find_by.side_effect = failure
    rules_repository.find_by_code.side_effect = failure
    rules_repository.list_all.side_effect = failure
    service = ReceiptRulesService(rules_repository)
    with patch(f"{MODULE}.log_service_success") as success:
        with pytest.raises(HTTPException) as caught:
            if operation == "create":
                await service.create(
                    user, ReceiptRulesCreateSchema(name="Bank", institution_code="BANK")
                )
            elif operation == "update":
                await service.update(uuid4(), ReceiptRulesUpdateSchema(), user)
            elif operation == "list_all":
                await service.list_all(ReceiptRulesFilter(), user)
            elif operation == "seed_defaults":
                await service.seed_defaults(user)
            else:
                await getattr(service, operation)(uuid4(), user)
    assert caught.value.status_code == 500 and caught.value.__cause__ is failure
    success.assert_not_called()


async def test_commit_failure_does_not_read_expired_user_metadata(rules_repository):
    expired = False
    owner_id = uuid4()

    class ExpiringUser:
        @property
        def id(self):
            assert not expired
            return owner_id

        @property
        def username(self):
            assert not expired
            return "owner"

    @asynccontextmanager
    async def fail_commit():
        nonlocal expired
        yield
        expired = True
        raise RuntimeError("commit failed")

    rules_repository.transaction = fail_commit
    with patch(f"{MODULE}.log_service_success") as success:
        with pytest.raises(HTTPException) as caught:
            await ReceiptRulesService(rules_repository).create(
                ExpiringUser(),
                ReceiptRulesCreateSchema(name="Bank", institution_code="BANK"),
            )
    assert caught.value.status_code == 500
    assert isinstance(caught.value.__cause__, RuntimeError)
    success.assert_not_called()


async def test_integrity_translation_only_recognizes_known_constraint():
    diagnostic = RuntimeError("duplicate")
    diagnostic.diag = SimpleNamespace(
        constraint_name="uq_receipt_profiles_owner_institution_live"
    )
    wrapper = RuntimeError("wrapped")
    wrapper.__cause__ = diagnostic
    error = ReceiptRulesService._translate_error(IntegrityError("insert", {}, wrapper))
    assert isinstance(error, HTTPException) and error.status_code == 409
    unknown = IntegrityError("insert", {}, RuntimeError("unknown constraint"))
    assert ReceiptRulesService._translate_error(unknown) is unknown


@pytest.mark.parametrize(
    "unavailable", ["profile", "rule", "inactive_rule", "deleted_rule"]
)
async def test_source_skips_unavailable_rules(
    rules_repository, user, profile, unavailable
):
    rules_repository.find_by.return_value = profile
    if unavailable == "profile":
        profile.is_active = False
    elif unavailable != "rule":
        rule = profile.field_rules[0]
        rule.field_name = "source_institution"
        if unavailable == "inactive_rule":
            rule.is_active = False
        else:
            rule.deleted_at = profile.created_at
    with patch(f"{MODULE}.extract_source", AsyncMock()) as engine:
        result = await ReceiptRulesService(rules_repository).extract_source_institution(
            profile.id, "text", user, identified=False
        )
    assert result.status == "not_found"
    engine.assert_not_awaited()


async def test_invalid_persisted_rule_and_engine_failures_are_explicit(
    rules_repository, user, profile
):
    rule = profile.field_rules[0]
    rule.field_name = "source_institution"
    rule.configuration = {"strategy": "constant", "value": "Bank"}
    rules_repository.find_by.return_value = profile
    service = ReceiptRulesService(rules_repository)
    with patch(
        f"{MODULE}.extract_source", AsyncMock(side_effect=RuntimeError("timeout"))
    ):
        with pytest.raises(HTTPException) as caught:
            await service.extract_source_institution(
                profile.id, "", user, identified=True
            )
    assert caught.value.status_code == 500
    rule.configuration = {"strategy": "unknown"}
    with pytest.raises(HTTPException) as caught:
        await service.find_by(profile.id, user)
    assert caught.value.status_code == 500
