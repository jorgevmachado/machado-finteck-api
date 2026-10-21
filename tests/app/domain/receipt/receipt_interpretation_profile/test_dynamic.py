import asyncio
import multiprocessing
from uuid import uuid4

import pytest

from app.domain.receipt.data.enums import DataStatusEnum
from app.domain.receipt.interpretation.dynamic import (
    ReceiptRuleExecutionError,
    _run_isolated,
    interpret_isolated,
    interpret_profiles,
)
from app.domain.receipt.interpretation.interpreters.base import BaseInterpreter
from app.domain.receipt.interpretation.interpreters.caixa import CaixaInterpreter
from app.domain.receipt.interpretation.interpreters.itau import ItauInterpreter
from app.domain.receipt.interpretation.interpreters.nubank import NubankInterpreter
from app.domain.receipt.interpretation.institutions.schema import InstitutionEnum
from app.domain.receipt.interpretation.schema import InterpretationConfigurationSnapshot
from app.domain.receipt.receipt_interpretation_profile.schema import (
    ReceiptInterpretationProfileSchema,
)
from app.domain.receipt.receipt_interpretation_profile.seed import load_seed_profiles
from app.models import (
    ReceiptFieldRule,
    ReceiptIdentificationRule,
    ReceiptInterpretationProfile,
)


def seed_snapshots():
    general, private = load_seed_profiles()
    profiles = []
    owner_id = uuid4()
    for payload in (general, *private):
        entity = ReceiptInterpretationProfile(
            user_id=owner_id if payload.institution_code else None,
            name=payload.name,
            institution_code=payload.institution_code,
        )
        entity.field_rules.extend(
            ReceiptFieldRule(profile_id=entity.id, **rule.model_dump(mode="json"))
            for rule in payload.field_rules
        )
        entity.identification_rules.extend(
            ReceiptIdentificationRule(
                profile_id=entity.id, **rule.model_dump(mode="json")
            )
            for rule in payload.identification_rules
        )
        profiles.append(ReceiptInterpretationProfileSchema.model_validate(entity))
    return profiles


@pytest.mark.parametrize(
    "code,interpreter,institution,text",
    [
        (
            "NUBANK",
            NubankInterpreter(),
            InstitutionEnum.NUBANK,
            "NU PAGAMENTOS S.A.\nComprovante de Pix\nR$ 1.234,56\nPara\nEmpresa A\n"
            "Pagamento realizado em: 01/02/2026\nVencimento 04 MAR 2026\n"
            "NI FEV 2026 - 12:30:00\nNome do pagador: Cliente\n"
            "Código de barras: 123 456 789\nID da transação: E123\n",
        ),
        (
            "ITAU",
            ItauInterpreter(),
            InstitutionEnum.ITAU,
            "ITAU UNIBANCO\nAutenticação digital Itaú: ABC123\n"
            "Valor pago: R$ 50,00\nNome do beneficiário: Empresa\n"
            "Data do pagamento: 03/02/2026\nNome do pagador: Cliente\n",
        ),
        (
            "CAIXA",
            CaixaInterpreter(),
            InstitutionEnum.CAIXA,
            "CAIXA ECONOMICA FEDERAL\nValor Pago (R$): 10,00\n"
            "Data de débito: 05/02/2026\nFavorecido Empresa\n"
            "Banco Recebedor: CAIXA ECONOMICA FEDERAL\n",
        ),
        (
            None,
            BaseInterpreter(),
            InstitutionEnum.UNKNOWN,
            "Valor pago: R$ 5,00\nNome do pagador: Cliente\n"
            "Nome do pagador efetivo: Outro\nValor do documento: R$ 4,00\n"
            "Juros/Mora: R$ 1,00\nMulta: R$ 2,00\nDesconto: R$ 0,50\n"
            "Total de encargos: R$ 3,00\nData do pagamento: 02/02/2026\n"
            "Instituição Emissora: 123 - Banco Outro\n",
        ),
    ],
)
def test_dynamic_seed_preserves_interpreter_outputs(
    code, interpreter, institution, text
):
    profiles = seed_snapshots()
    result = interpret_profiles(text, profiles)
    assert result.data == interpreter.interpret(text, institution)
    selected = result.configuration.selected_profile_id
    assert selected == next(
        (p.id for p in profiles if p.institution_code == code and code is not None),
        None,
    )


def test_inheritance_no_match_no_general_retry_and_inactive_override():
    profiles = seed_snapshots()
    nubank = profiles[1]
    general_payment = profiles[0].field_rules[
        next(
            i
            for i, r in enumerate(profiles[0].field_rules)
            if r.field_name == "payment_date"
        )
    ]
    text = "NU PAGAMENTOS\nData do pagamento: 01/02/2026\nValor pago: R$ 10,00"
    result = interpret_profiles(text, profiles)
    assert result.data.payment_date.status == DataStatusEnum.NOT_FOUND
    override = next(r for r in nubank.field_rules if r.field_name == "payment_date")
    override.is_active = False
    assert (
        interpret_profiles(text, profiles).data.payment_date.value.isoformat()
        == "2026-02-01"
    )
    nubank.field_rules = [
        r for r in nubank.field_rules if r.field_name != "payment_date"
    ]
    assert (
        interpret_profiles(text, profiles).data.payment_date
        == interpret_profiles(text, [profiles[0]]).data.payment_date
    )
    assert general_payment.is_active


def test_tie_unknown_disabled_and_empty_text_use_general_without_constants():
    profiles = seed_snapshots()
    for text in ("", "sem instituicao", "BANCO NU\nITAU.COM.BR"):
        result = interpret_profiles(text, profiles)
        assert result.configuration.selected_profile_id is None
        assert result.data.source_institution.status == DataStatusEnum.NOT_FOUND
    profiles[1].is_active = False
    assert (
        interpret_profiles("NU PAGAMENTOS", profiles).configuration.selected_profile_id
        is None
    )
    with pytest.raises(ReceiptRuleExecutionError, match="General"):
        interpret_profiles("anything", profiles[1:])


def test_ambiguous_and_not_found_fallbacks_and_optional_capture():
    profiles = seed_snapshots()
    result = interpret_profiles(
        "Data do pagamento: 31/02/2026\nValor pago: R$ 12,00\nNome do pagador: Nome\n",
        profiles,
    )
    assert result.data.payment_date.status == DataStatusEnum.AMBIGUOUS
    assert result.data.document_amount == result.data.paid_amount
    assert result.data.effective_payer == result.data.payer
    rule = next(r for r in profiles[0].field_rules if r.field_name == "payer")
    rule.configuration.patterns = ["(?P<value>x)?y"]
    assert (
        interpret_profiles("y", profiles).data.payer.status == DataStatusEnum.AMBIGUOUS
    )


@pytest.mark.asyncio
async def test_isolated_worker_returns_snapshot_and_stops_after_catastrophic_regex():
    profiles = seed_snapshots()
    result = await interpret_isolated("ITAU UNIBANCO\nValor pago: R$ 15,00", profiles)
    assert result.data.paid_amount.value == 15
    assert result.configuration.profiles == profiles
    rule = next(r for r in profiles[0].field_rules if r.field_name == "payer")
    rule.configuration.patterns = [r"(?P<value>(a+)+)$"]
    configuration = InterpretationConfigurationSnapshot(
        selected_profile_id=None, profiles=profiles
    ).model_dump_json()
    existing_children = {child.pid for child in multiprocessing.active_children()}
    with pytest.raises(ReceiptRuleExecutionError, match="timed out"):
        await asyncio.to_thread(_run_isolated, "a" * 100_000 + "!", configuration, 1.0)
    assert {
        child.pid for child in multiprocessing.active_children()
    } == existing_children


@pytest.mark.asyncio
async def test_execution_input_caps():
    with pytest.raises(ReceiptRuleExecutionError, match="text"):
        await interpret_isolated("x" * 1_000_001, [])
    profiles = seed_snapshots()
    with pytest.raises(ReceiptRuleExecutionError, match="count"):
        await interpret_isolated("text", [profiles[0]] * 101)
