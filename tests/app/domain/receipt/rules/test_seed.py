from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.domain.receipt.rules.defaults import load_default_receipt_rules
from app.domain.receipt.rules.schema import (
    ReceiptRulesCreateSchema,
    ReceiptRulesSeedEntrySchema,
)
from app.domain.receipt.rules.service import ReceiptRulesService

MODULE = "app.domain.receipt.rules.service"


def test_catalog_accepts_shared_general_without_weakening_public_create():
    payloads = load_default_receipt_rules()
    general = [p for p in payloads if p.institution_code is None]
    assert len(general) == 1
    assert len(general[0].field_rules) == 18
    assert general[0].identification_rules == []
    assert {p.institution_code for p in payloads} == {None, "NUBANK", "ITAU", "CAIXA"}
    with pytest.raises(ValidationError):
        ReceiptRulesCreateSchema(name="General", institution_code=None)
    with pytest.raises(ValidationError):
        ReceiptRulesSeedEntrySchema(
            name="General",
            institution_code=None,
            identification_rules=[{"pattern": "bank", "weight": 1}],
        )


@pytest.fixture
def repository():
    repo = SimpleNamespace(
        find_by_code=AsyncMock(return_value=None),
        lock_seed=AsyncMock(),
        save=AsyncMock(),
        committed=False,
        entered=0,
        rolled_back=False,
    )

    @asynccontextmanager
    async def transaction():
        repo.entered += 1
        assert repo.entered == 1, "Nested transaction"
        try:
            yield
            repo.committed = True
        except BaseException:
            repo.rolled_back = True
            raise

    repo.transaction = transaction
    return repo


@pytest.mark.asyncio
async def test_seed_uses_one_transaction_and_correct_scope(repository, user):
    service = ReceiptRulesService(repository)
    with patch(f"{MODULE}.log_service_success") as success:
        success.side_effect = lambda *args, **kwargs: (
            None if repository.committed else pytest.fail("Success before commit")
        )
        result = await service.seed_defaults(user)
    assert result.model_dump() == {"created": 4, "skipped": 0}
    repository.lock_seed.assert_awaited_once()
    entities = [call.args[0] for call in repository.save.await_args_list]
    general = next(entity for entity in entities if entity.institution_code is None)
    assert general.user_id is None
    assert len(general.field_rules) == 18
    for entity in entities:
        if entity.institution_code is not None:
            assert entity.user_id == user.id
            assert entity.identification_rules
        assert all(child.profile_id == entity.id for child in entity.field_rules)
    assert repository.entered == 1
    assert success.call_args.kwargs["operation"] == "seed_defaults"


@pytest.mark.asyncio
async def test_seed_skips_by_code_not_display_name(repository, user):
    repository.find_by_code.return_value = SimpleNamespace(name="Renamed")
    result = await ReceiptRulesService(repository).seed_defaults(user)
    assert result.model_dump() == {"created": 0, "skipped": 4}
    repository.save.assert_not_awaited()
    assert {
        (call.kwargs["user_id"], call.kwargs["institution_code"])
        for call in repository.find_by_code.await_args_list
    } == {(None, None), (user.id, "NUBANK"), (user.id, "ITAU"), (user.id, "CAIXA")}


@pytest.mark.asyncio
async def test_seed_failure_is_handled_and_never_logged_as_success(repository, user):
    repository.save.side_effect = RuntimeError("save failed")
    with patch(f"{MODULE}.log_service_success") as success:
        with pytest.raises(HTTPException) as caught:
            await ReceiptRulesService(repository).seed_defaults(user)
    assert caught.value.status_code == 500
    assert repository.rolled_back
    assert not repository.committed
    success.assert_not_called()


@pytest.mark.asyncio
async def test_catalog_validation_failure_uses_standard_handler(repository, user):
    with patch(
        f"{MODULE}.load_default_receipt_rules", side_effect=ValueError("bad catalog")
    ):
        with patch(f"{MODULE}.log_service_success") as success:
            with pytest.raises(HTTPException) as caught:
                await ReceiptRulesService(repository).seed_defaults(user)
    assert caught.value.status_code == 500
    assert repository.entered == 0
    success.assert_not_called()


@pytest.mark.asyncio
async def test_normal_create_uses_code_query(repository, user):
    service = ReceiptRulesService(repository)
    payload = ReceiptRulesCreateSchema(name="Bank", institution_code="BANK")
    result = await service.create(user, payload)
    assert result.institution_code == "BANK"
    repository.find_by_code.assert_awaited_once_with(
        user_id=user.id, institution_code="BANK"
    )


@pytest.mark.asyncio
async def test_seed_second_owner_preserves_shared_general_and_creates_private_banks(
    repository, user
):
    repository.find_by_code.side_effect = [
        SimpleNamespace(name="General"),
        None,
        None,
        None,
    ]
    result = await ReceiptRulesService(repository).seed_defaults(user)
    assert result.model_dump() == {"created": 3, "skipped": 1}
    entities = [call.args[0] for call in repository.save.await_args_list]
    assert {entity.institution_code for entity in entities} == {
        "NUBANK",
        "ITAU",
        "CAIXA",
    }
    assert all(entity.user_id == user.id for entity in entities)
    caixa = next(entity for entity in entities if entity.institution_code == "CAIXA")
    assert caixa.field_rules[0].configuration["strategy"] == "source"


@pytest.mark.asyncio
async def test_seed_second_save_failure_aborts_transaction(repository, user):
    repository.save.side_effect = [None, RuntimeError("second save failed")]
    with pytest.raises(HTTPException):
        await ReceiptRulesService(repository).seed_defaults(user)
    assert repository.save.await_count == 2
    assert repository.rolled_back and not repository.committed


def test_catalog_rejects_duplicate_profile_codes(monkeypatch):
    from pathlib import Path

    data = '[{"name":"One","institution_code":"BANK"},{"name":"Two","institution_code":"BANK"}]'
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: data)
    with pytest.raises(ValueError, match="duplicate"):
        load_default_receipt_rules()
