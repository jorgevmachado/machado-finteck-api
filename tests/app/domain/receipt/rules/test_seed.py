from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.domain.receipt.rules.defaults import load_default_receipt_rules
from app.domain.receipt.rules.schema import (
    ReceiptRulesCreateSchema,
    ReceiptRulesSeedEntrySchema,
)
from app.domain.receipt.rules.service import ReceiptRulesService
from app.shared.utils.string import to_snake_case

MODULE = "app.domain.receipt.rules.service"


def test_catalog_accepts_shared_general_without_weakening_public_create():
    payloads = load_default_receipt_rules()
    general = [p for p in payloads if p.institution_name is None]
    assert len(general) == 1
    assert len(general[0].field_rules) == 18
    assert general[0].identification_rules == []
    assert {p.institution_name for p in payloads} == {
        None,
        "Nu Pagamentos",
        "Itaú Unibanco",
        "Caixa Econômica Federal",
    }
    with pytest.raises(ValidationError):
        ReceiptRulesCreateSchema(name="General", institution_id=None)
    with pytest.raises(ValidationError):
        ReceiptRulesSeedEntrySchema(
            name="General",
            institution_name=None,
            identification_rules=[{"pattern": "bank", "weight": 1}],
        )


SEED_INSTITUTIONS = {
    "Nu Pagamentos": uuid4(),
    "Itaú Unibanco": uuid4(),
    "Caixa Econômica Federal": uuid4(),
}


def institution_stub(name: str):
    return SimpleNamespace(
        id=SEED_INSTITUTIONS[name], name=name, name_code=to_snake_case(name)
    )


@pytest.fixture
def repository():
    repo = SimpleNamespace(
        find_by_institution=AsyncMock(return_value=None),
        lock_seed=AsyncMock(),
        save_profile=AsyncMock(),
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


@pytest.fixture
def service(repository):
    """Service com `InstitutionService` substituído por um stub idempotente."""
    instance = ReceiptRulesService(repository)

    def resolve(_user, name: str):
        return institution_stub(name)

    async def resolve_async(user, name: str):
        return resolve(user, name)

    stub = SimpleNamespace(
        resolve=AsyncMock(side_effect=resolve_async),
        resolve_in_transaction=AsyncMock(side_effect=resolve_async),
    )
    with patch.object(
        ReceiptRulesService,
        "institution_service",
        new_callable=PropertyMock,
        return_value=stub,
    ):
        yield instance


@pytest.mark.asyncio
async def test_seed_uses_one_transaction_and_correct_scope(service, repository, user):
    with patch("app.core.service.base.log_service_success") as success:
        success.side_effect = lambda *args, **kwargs: (
            None if repository.committed else pytest.fail("Success before commit")
        )
        result = await service.seed_defaults(user)
    assert result.model_dump() == {"created": 4, "skipped": 0}
    repository.lock_seed.assert_awaited_once()
    entities = [call.args[0] for call in repository.save_profile.await_args_list]
    general = next(entity for entity in entities if entity.institution_id is None)
    assert general.user_id is None
    assert general.institution_code is None
    assert len(general.field_rules) == 18
    for entity in entities:
        if entity.institution_id is not None:
            assert entity.user_id == user.id
            assert entity.identification_rules
        assert all(child.profile_id == entity.id for child in entity.field_rules)
    assert {
        entity.institution_code for entity in entities if entity.institution_id
    } == {
        "NU_PAGAMENTOS",
        "ITAU_UNIBANCO",
        "CAIXA_ECONOMICA_FEDERAL",
    }
    assert repository.entered == 1
    assert success.call_args.kwargs["operation"] == "seed_defaults"


@pytest.mark.asyncio
async def test_seed_skips_by_institution_not_display_name(service, repository, user):
    repository.find_by_institution.return_value = SimpleNamespace(name="Renamed")
    result = await service.seed_defaults(user)
    assert result.model_dump() == {"created": 0, "skipped": 4}
    repository.save_profile.assert_not_awaited()
    assert {
        (call.kwargs["user_id"], call.kwargs["institution_id"])
        for call in repository.find_by_institution.await_args_list
    } == {
        (None, None),
        (user.id, SEED_INSTITUTIONS["Nu Pagamentos"]),
        (user.id, SEED_INSTITUTIONS["Itaú Unibanco"]),
        (user.id, SEED_INSTITUTIONS["Caixa Econômica Federal"]),
    }


@pytest.mark.asyncio
async def test_seed_failure_is_handled_and_never_logged_as_success(
    service, repository, user
):
    repository.save_profile.side_effect = RuntimeError("save failed")
    with patch("app.core.service.base.log_service_success") as success:
        with pytest.raises(HTTPException) as caught:
            await service.seed_defaults(user)
    assert caught.value.status_code == 500
    assert repository.rolled_back
    assert not repository.committed
    success.assert_not_called()


@pytest.mark.asyncio
async def test_catalog_validation_failure_uses_standard_handler(
    service, repository, user
):
    with patch(
        f"{MODULE}.load_default_receipt_rules", side_effect=ValueError("bad catalog")
    ):
        with patch("app.core.service.base.log_service_success") as success:
            with pytest.raises(HTTPException) as caught:
                await service.seed_defaults(user)
    assert caught.value.status_code == 500
    assert repository.entered == 0
    success.assert_not_called()


@pytest.mark.asyncio
async def test_normal_create_derives_code_from_institution_name_code(
    service, repository, user
):
    institution = SimpleNamespace(id=uuid4(), name="Bank", name_code="meu_banco")
    service.institution_service.find_by = AsyncMock(return_value=institution)
    payload = ReceiptRulesCreateSchema(name="Bank", institution_id=institution.id)
    result = await service.create_profile(user, payload)
    assert result.institution_id == institution.id
    assert result.institution_code == "MEU_BANCO"
    repository.find_by_institution.assert_awaited_once_with(
        user_id=user.id, institution_id=institution.id
    )


@pytest.mark.asyncio
async def test_seed_second_owner_preserves_shared_general_and_creates_private_banks(
    service, repository, user
):
    repository.find_by_institution.side_effect = [
        SimpleNamespace(name="General"),
        None,
        None,
        None,
    ]
    result = await service.seed_defaults(user)
    assert result.model_dump() == {"created": 3, "skipped": 1}
    entities = [call.args[0] for call in repository.save_profile.await_args_list]
    assert {entity.institution_code for entity in entities} == {
        "NU_PAGAMENTOS",
        "ITAU_UNIBANCO",
        "CAIXA_ECONOMICA_FEDERAL",
    }
    assert all(entity.user_id == user.id for entity in entities)
    caixa = next(
        entity
        for entity in entities
        if entity.institution_code == "CAIXA_ECONOMICA_FEDERAL"
    )
    assert caixa.field_rules[0].configuration["strategy"] == "source"


@pytest.mark.asyncio
async def test_seed_second_save_failure_aborts_transaction(service, repository, user):
    repository.save_profile.side_effect = [None, RuntimeError("second save failed")]
    with pytest.raises(HTTPException):
        await service.seed_defaults(user)
    assert repository.save_profile.await_count == 2
    assert repository.rolled_back and not repository.committed


def test_catalog_rejects_duplicate_institution_names(monkeypatch):
    from pathlib import Path

    data = (
        '[{"name":"One","institution_name":"Banco"},'
        '{"name":"Two","institution_name":"Banco"}]'
    )
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: data)
    with pytest.raises(ValueError, match="duplicate"):
        load_default_receipt_rules()
