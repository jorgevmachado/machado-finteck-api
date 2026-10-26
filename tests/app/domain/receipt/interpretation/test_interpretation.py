import subprocess
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.domain.receipt.interpretation import Interpretation
from app.domain.receipt.interpretation.institution.institution import find_institution
from app.domain.receipt.interpretation.institution.institution import _identify
from app.domain.receipt.rules.schema import ReceiptRulesSchema
from app.domain.receipt.rules.field.schema import ReceiptFieldRuleSchema
from app.models import (
    ReceiptFieldRule,
    ReceiptIdentificationRule,
    ReceiptInterpretationProfile,
    utcnow,
)


def profile(code, patterns, *, is_active=True):
    entity = ReceiptInterpretationProfile(
        user_id=uuid4(), name=code, institution_code=code, is_active=is_active
    )
    entity.identification_rules.extend(
        ReceiptIdentificationRule(
            profile_id=entity.id, pattern=pattern, weight=weight, is_active=active
        )
        for pattern, weight, active in patterns
    )
    return ReceiptRulesSchema.model_validate(entity)


def field_rule(field_name, *, is_active=True):
    return ReceiptFieldRuleSchema.model_validate(
        ReceiptFieldRule(
            profile_id=uuid4(),
            field_name=field_name,
            configuration={"strategy": "not_found"},
            is_active=is_active,
        )
    )


@pytest.mark.parametrize("default_first", [True, False])
def test_merge_keeps_defaults_and_overrides_by_identified_institution(
    default_first,
):
    default = ReceiptRulesSchema.model_validate(
        ReceiptInterpretationProfile(
            user_id=None, name="Default", institution_code=None
        )
    )
    due_date = field_rule("due_date")
    default_payment = field_rule("payment_date")
    default.field_rules = [due_date, default_payment]
    itau = profile("ITAU", [("itau", 10, True)])
    payment = field_rule("payment_date")
    payer = field_rule("payer")
    itau.field_rules = [payment, payer]
    other = profile("NUBANK", [("nubank", 10, True)])
    other.field_rules = [field_rule("due_date")]
    rules = [default, itau, other] if default_first else [itau, other, default]
    original_defaults = list(default.field_rules)
    interpretation = Interpretation(rules, "itau")
    result = interpretation.result()
    assert interpretation.institution == "ITAU"
    assert set(result.model_dump()) == {"data", "errors"}
    assert {rule.field_name: rule.id for rule in interpretation.interpreter.rules} == {
        "due_date": due_date.id,
        "payment_date": payment.id,
        "payer": payer.id,
    }
    assert default.field_rules == original_defaults
    assert itau.field_rules == [payment, payer]


def test_merge_uses_only_live_active_rules_and_defaults_for_unknown_institution():
    default = ReceiptRulesSchema.model_validate(
        ReceiptInterpretationProfile(
            user_id=None, name="Default", institution_code=None
        )
    )
    due_date = field_rule("due_date")
    default.field_rules = [due_date, field_rule("payer", is_active=False)]
    deleted_rule = field_rule("payment_date")
    deleted_rule.deleted_at = utcnow()
    default.field_rules.append(deleted_rule)
    itau = profile("ITAU", [("itau", 10, True)])
    itau.field_rules = [
        field_rule("due_date", is_active=False),
        field_rule("payment_date"),
    ]
    inactive = default.model_copy(
        update={"is_active": False, "field_rules": [field_rule("barcode")]}
    )
    deleted = default.model_copy(
        update={"deleted_at": utcnow(), "field_rules": [field_rule("beneficiary")]}
    )
    rules = [default, itau, inactive, deleted]
    interpretation = Interpretation(rules, "itau")
    assert {rule.field_name for rule in interpretation.interpreter.rules} == {
        "due_date",
        "payment_date",
    }

    interpretation = Interpretation(rules, "sem correspondencia")
    assert interpretation.institution == "unknow"
    assert interpretation.interpreter.rules == [due_date]


def test_merge_without_default_keeps_institution_fields():
    itau = profile("ITAU", [("itau", 10, True)])
    itau.field_rules = [field_rule("payment_date")]
    interpretation = Interpretation([itau], "itau")
    assert interpretation.interpreter.rules == itau.field_rules


def test_identification_sums_weights_once_per_matching_rule():
    rules = [
        profile("NUBANK", [("banco", 3, True), (r"nu\s+pagamentos", 4, True)]),
        profile("ITAU", [("banco", 6, True)]),
    ]
    assert _identify("BANCO banco Nu Pagamentos", rules) == "NUBANK"


@pytest.mark.parametrize("text", ["banco", "sem correspondencia", ""])
def test_ties_and_missing_matches_return_unknow(text):
    rules = [
        profile("NUBANK", [("banco", 5, True)]),
        profile("ITAU", [("banco", 5, True)]),
    ]
    assert _identify(text, rules) == "unknow"


def test_inactive_deleted_and_general_rules_do_not_identify():
    inactive = profile("NUBANK", [("banco", 100, True)], is_active=False)
    deleted = profile("ITAU", [("banco", 100, True)])
    deleted.deleted_at = utcnow()
    general = deleted.model_copy(update={"deleted_at": None, "institution_code": None})
    active = profile("CAIXA", [("banco", 100, False), ("banco", 100, True)])
    active.identification_rules[1].deleted_at = utcnow()
    assert _identify("banco", [inactive, deleted, general, active]) == "unknow"


def test_empty_rules_return_unknow():
    assert _identify("banco", []) == "unknow"


def test_unmatched_profiles_do_not_override_identified_institution():
    rules = [
        profile("ITAU", [("itau", 5, True)]),
        profile("NUBANK", [("nubank", 100, True)]),
    ]
    assert _identify("ITAU", rules) == "ITAU"


def test_institution_worker_limits_resources_and_serializes_result(monkeypatch):
    from io import StringIO
    from runpy import run_path

    import resource

    from app.domain.receipt.interpretation.institution import institution
    from app.domain.receipt.interpretation.schema import (
        InstitutionResult,
        InterpretationRequest,
    )

    request = InterpretationRequest(
        text="ITAU", rules=[profile("ITAU", [("itau", 5, True)])]
    )
    output = StringIO()
    monkeypatch.setattr(institution.sys, "stdin", StringIO(request.model_dump_json()))
    monkeypatch.setattr(institution.sys, "stdout", output)
    with patch.object(resource, "setrlimit") as limits:
        run_path(institution.__file__, run_name="__main__")
    assert (
        InstitutionResult.model_validate_json(output.getvalue()).institution == "ITAU"
    )
    limits.assert_any_call(resource.RLIMIT_CPU, (2, 2))
    limits.assert_any_call(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))


def test_oversized_text_returns_unknow_without_starting_process(caplog):
    with patch(
        "app.domain.receipt.interpretation.institution.institution.subprocess.run"
    ) as create_process:
        result = find_institution("a" * 1_000_001, [])
    assert result == "unknow"
    create_process.assert_not_called()
    assert "execution limit" in caplog.text


@pytest.mark.parametrize(
    "error",
    [
        subprocess.TimeoutExpired("institution", 3),
        subprocess.CalledProcessError(1, "institution"),
        OSError("Cannot start interpreter"),
    ],
)
def test_process_failure_returns_unknow_and_logs(error, caplog):
    with patch(
        "app.domain.receipt.interpretation.institution.institution.subprocess.run",
        side_effect=error,
    ):
        result = find_institution("banco", [])
    assert result == "unknow"
    assert caplog.records


def test_invalid_process_output_returns_unknow_and_logs(caplog):
    with patch(
        "app.domain.receipt.interpretation.institution.institution.subprocess.run",
        return_value=SimpleNamespace(stdout=b"invalid json"),
    ):
        result = find_institution("banco", [])
    assert result == "unknow"
    assert caplog.records
