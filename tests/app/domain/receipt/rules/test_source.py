from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.domain.receipt.rules.configuration.engine import (
    SourceExecutionRequest,
    _extract,
    extract_source,
)
from app.domain.receipt.rules.configuration import engine
from app.domain.receipt.rules.defaults import load_default_receipt_rules
from app.domain.receipt.rules.field.schema import ReceiptFieldRuleCreateSchema
from app.domain.receipt.rules.service import ReceiptRulesService
from app.models import ReceiptFieldRule, ReceiptInterpretationProfile


def source_rule(code):
    profile = next(
        p for p in load_default_receipt_rules() if p.institution_code == code
    )
    return next(r for r in profile.field_rules if r.field_name == "source_institution")


@pytest.mark.parametrize(
    "code,text,identified,expected,status",
    [
        ("NUBANK", "", True, "Nubank", "found"),
        ("ITAU", "", True, "Itaú", "found"),
        ("CAIXA", "", True, "Caixa", "found"),
        ("NUBANK", "origem nu pagamentos", False, "Nubank", "found"),
        ("NUBANK", "nubank.com.br", False, "Nubank", "found"),
        ("ITAU", "ITAU UNIBANCO", False, "Itaú", "found"),
        ("ITAU", "ITAÚ UNIBANCO", False, "Itaú", "found"),
        ("ITAU", "Autenticação Digital Itaú", False, "Itaú", "found"),
        (
            "CAIXA",
            "Banco Recebedor: CAIXA ECONOMICA FEDERAL\n",
            False,
            "Caixa",
            "found",
        ),
        (
            "CAIXA",
            "Banco Recebedor: caixa econômica federal\n",
            False,
            "Caixa",
            "found",
        ),
        (
            "CAIXA",
            "Banco Recebedor: Banco Diferente\n",
            False,
            "Banco Diferente",
            "found",
        ),
        ("CAIXA", "Banco Recebedor: Outro Pagador Final", False, "Outro", "found"),
        ("CAIXA", "Banco Recebedor:   \n", False, None, "ambiguous"),
        ("NUBANK", "sem evidencia", False, None, "not_found"),
        ("ITAU", "sem evidencia", False, None, "not_found"),
        ("CAIXA", "sem evidencia", False, None, "not_found"),
    ],
)
def test_source_matches_original_methods(code, text, identified, expected, status):
    result = _extract(
        SourceExecutionRequest(rule=source_rule(code), text=text, identified=identified)
    )
    assert result.value == expected
    assert result.status == status


def test_names_conditions_and_mappings_are_data_not_bank_branches():
    rule = ReceiptFieldRuleCreateSchema(
        field_name="source_institution",
        configuration={
            "strategy": "source",
            "identified_value": "Novo Banco",
            "matches": [{"contains": "nova marca", "value": "Banco Novo"}],
            "extraction": {
                "strategy": "regex",
                "parser": "text",
                "patterns": ["Origem: (?P<value>[^\\n]+)"],
            },
            "mappings": [{"contains": "empresa nova", "value": "Empresa Normalizada"}],
        },
    )
    for text, identified, expected in (
        ("", True, "Novo Banco"),
        ("NOVA MARCA", False, "Banco Novo"),
        ("Origem: EMPRESA NOVA\n", False, "Empresa Normalizada"),
        ("Origem: Terceiro\n", False, "Terceiro"),
    ):
        assert (
            _extract(
                SourceExecutionRequest(rule=rule, text=text, identified=identified)
            ).value
            == expected
        )
    rule.is_active = False
    assert (
        _extract(
            SourceExecutionRequest(rule=rule, text="nova marca", identified=True)
        ).status
        == "not_found"
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"identified_value": " "},
        {"matches": [{"contains": "", "value": "X"}]},
        {"mappings": [{"contains": "X", "value": " "}]},
        {
            "extraction": {
                "strategy": "regex",
                "parser": "decimal_br",
                "patterns": ["(?P<value>x)"],
            }
        },
        {"extraction": {"strategy": "regex", "parser": "text", "patterns": ["(x)"]}},
        {"unknown": "value"},
    ],
)
def test_source_configuration_rejects_invalid_or_untyped_conditions(patch):
    with pytest.raises(ValidationError):
        ReceiptFieldRuleCreateSchema(
            field_name="source_institution",
            configuration={"strategy": "source", "identified_value": "Bank"} | patch,
        )
    with pytest.raises(ValidationError):
        ReceiptFieldRuleCreateSchema(
            field_name="payer",
            configuration={"strategy": "source", "identified_value": "Bank"},
        )


@pytest.mark.asyncio
async def test_engine_serializes_rule_and_input_and_validates_worker_response():
    process = SimpleNamespace(
        communicate=AsyncMock(
            return_value=(b'{"status":"found","value":"Caixa"}', b"")
        ),
        returncode=0,
        wait=AsyncMock(),
    )
    rule = source_rule("CAIXA")
    with patch.object(
        engine.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    ) as start:
        result = await extract_source(
            rule, "Banco Recebedor: Caixa\n", identified=False
        )
    assert result.value == "Caixa"
    request = SourceExecutionRequest.model_validate_json(
        process.communicate.await_args.args[0]
    )
    assert request.rule == rule
    assert request.text == "Banco Recebedor: Caixa\n" and not request.identified
    assert start.await_args.args[1:] == ("-m", engine.__name__)
    process.wait.assert_awaited_once()
    with pytest.raises(ValueError, match="limit"):
        await extract_source(rule, "x" * 1_000_001, identified=False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "returncode,stdout,error",
    [
        (1, b"", RuntimeError),
        (0, b'{"status":"invalid"}', ValidationError),
    ],
)
async def test_worker_failure_or_invalid_output_is_not_success(
    returncode, stdout, error
):
    process = SimpleNamespace(
        communicate=AsyncMock(return_value=(stdout, b"worker error")),
        returncode=returncode,
        wait=AsyncMock(),
    )
    with patch.object(
        engine.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    ):
        with pytest.raises(error):
            await extract_source(source_rule("CAIXA"), "text", identified=False)
    process.wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_timeout_kills_worker(monkeypatch):
    process = SimpleNamespace(
        communicate=AsyncMock(return_value=(b"", b"")),
        returncode=None,
        kill=lambda: setattr(process, "returncode", -9),
        wait=AsyncMock(),
    )

    async def timeout(awaitable, **kwargs):
        awaitable.close()
        raise TimeoutError

    with patch.object(
        engine.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    ):
        monkeypatch.setattr(engine.asyncio, "wait_for", timeout)
        with pytest.raises(RuntimeError, match="timed out"):
            await extract_source(source_rule("CAIXA"), "", identified=False)
    assert process.returncode == -9
    process.wait.assert_awaited_once()


def test_source_engine_handles_legacy_regex_constant_not_found_and_missing_capture():
    for configuration, text, status, value in (
        ({"strategy": "constant", "value": "Any Bank"}, "", "found", "Any Bank"),
        ({"strategy": "not_found"}, "Bank", "not_found", None),
        (
            {
                "strategy": "regex",
                "parser": "text",
                "patterns": ["No match: (?P<value>x)", "Bank: (?P<value>.+)"],
            },
            "Bank:  Example  ",
            "found",
            "Example",
        ),
        (
            {"strategy": "regex", "parser": "text", "patterns": ["(?P<value>x)?y"]},
            "y",
            "ambiguous",
            None,
        ),
    ):
        rule = ReceiptFieldRuleCreateSchema(
            field_name="source_institution", configuration=configuration
        )
        result = _extract(
            SourceExecutionRequest(rule=rule, text=text, identified=False)
        )
        assert result.status == status and result.value == value


@pytest.mark.asyncio
async def test_wrong_field_is_rejected_before_starting_worker():
    rule = ReceiptFieldRuleCreateSchema(
        field_name="payer", configuration={"strategy": "not_found"}
    )
    with pytest.raises(ValueError, match="source_institution"):
        _extract(SourceExecutionRequest(rule=rule, text="", identified=False))
    with patch.object(engine.asyncio, "create_subprocess_exec", AsyncMock()) as start:
        with pytest.raises(ValueError, match="source_institution"):
            await extract_source(rule, "", identified=False)
    start.assert_not_awaited()


def test_worker_entrypoint_sets_resource_limits_and_serializes_output(monkeypatch):
    from io import StringIO
    from runpy import run_path

    import resource

    request = SourceExecutionRequest(
        rule=source_rule("CAIXA"), text="", identified=True
    )
    output = StringIO()
    monkeypatch.setattr(engine.sys, "stdin", StringIO(request.model_dump_json()))
    monkeypatch.setattr(engine.sys, "stdout", output)
    with patch.object(resource, "setrlimit", Mock()) as limits:
        run_path(engine.__file__, run_name="__main__")
    assert (
        engine.SourceExtractionResult.model_validate_json(output.getvalue()).value
        == "Caixa"
    )
    limits.assert_any_call(resource.RLIMIT_CPU, (2, 2))
    limits.assert_any_call(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))


@pytest.mark.asyncio
async def test_service_reads_current_owned_rule_and_blocks_missing_profile(user):
    entity = ReceiptInterpretationProfile(
        user_id=user.id, name="Caixa", institution_code="CAIXA"
    )
    entity.field_rules.append(
        ReceiptFieldRule(
            profile_id=entity.id,
            **source_rule("CAIXA").model_dump(mode="json"),
        )
    )
    repository = SimpleNamespace(find_by=AsyncMock(return_value=entity))
    service = ReceiptRulesService(repository)
    result = await service.extract_source_institution(
        entity.id, "Banco Recebedor: Banco Novo\n", user, identified=False
    )
    assert result.value == "Banco Novo"
    repository.find_by.assert_awaited_once_with(id=entity.id, user_id=user.id)
    entity.field_rules[0].configuration["identified_value"] = "Nome editado"
    result = await service.extract_source_institution(
        entity.id, "", user, identified=True
    )
    assert result.value == "Nome editado"
    repository.find_by.return_value = None
    with pytest.raises(HTTPException) as caught:
        await service.extract_source_institution(uuid4(), "", user, identified=False)
    assert caught.value.status_code == 404
