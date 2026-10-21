import ast
import json
import re
from pathlib import Path

import pytest

from app.domain.receipt.data.schema import ReceiptData
from app.domain.receipt.receipt_interpretation_profile.schema import (
    ReceiptFieldRuleCreateSchema,
)

PROFILE_DIR = Path("app/domain/receipt/receipt_interpretation_profile")
INTERPRETER_DIR = Path("app/domain/receipt/interpretation/interpreters")

GENERAL = json.loads((PROFILE_DIR / "general_profile.json").read_text("utf-8"))
DEFAULTS = {
    item["institution_code"]: item
    for item in json.loads((PROFILE_DIR / "default_profiles.json").read_text("utf-8"))
}

DATE_GROUPS = {
    r"\d{2}/\d{2}/\d{4}": r"(\d{2})/(\d{2})/(\d{4})",
    r"\d{2}\s+[A-Z]{3}\s+\d{4}": r"(\d{2})\s+([A-Z]{3})\s+(\d{4})",
    r"[0-9NIL]{2}\s+[A-Z]{3}\s+\d{4}": r"([0-9NIL]{2})\s+([A-Z]{3})\s+(\d{4})",
}


def rules_by_field(profile):
    return {rule["field_name"]: rule for rule in profile["field_rules"]}


def original_patterns(file_name, method):
    tree = ast.parse((INTERPRETER_DIR / file_name).read_text("utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == method
    )
    return [
        node.value
        for node in ast.walk(function)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and ("\\" in node.value or "(" in node.value)
        and node.value != r"\s+"
    ]


def restore_captures(pattern):
    restored = re.sub(
        r"\(\?P<value>(\\d\{2\}/.+?\\d\{4\}|\\d\{2\}\\s\+.+?\\d\{4\}|\[0-9NIL\].+?\\d\{4\})\)",
        lambda match: DATE_GROUPS[match.group(1)],
        pattern,
    )
    return restored.replace("(?P<value>", "(")


@pytest.mark.parametrize(
    "rule",
    GENERAL["field_rules"]
    + [rule for item in DEFAULTS.values() for rule in item["field_rules"]],
)
def test_every_seed_field_rule_is_schema_valid(rule):
    ReceiptFieldRuleCreateSchema.model_validate(rule)


def test_general_profile_covers_exactly_receipt_data_fields():
    names = [rule["field_name"] for rule in GENERAL["field_rules"]]
    assert len(names) == 18
    assert names == list(ReceiptData.model_fields)
    assert GENERAL["name"] == "Geral"
    assert GENERAL["institution_code"] is None
    assert GENERAL["identification_rules"] == []


def test_general_not_found_fields_and_fallbacks():
    rules = rules_by_field(GENERAL)
    not_found = {
        name
        for name, rule in rules.items()
        if rule["configuration"]["strategy"] == "not_found"
    }
    assert not_found == {
        "category",
        "description",
        "authentication",
        "source_institution",
    }
    fallbacks = {
        name: rule["configuration"]["fallback_field"]
        for name, rule in rules.items()
        if rule["configuration"].get("fallback_field")
    }
    assert fallbacks == {"effective_payer": "payer", "document_amount": "paid_amount"}
    assert rules["barcode"]["configuration"]["normalization"] == "remove_whitespace"
    assert len(rules["beneficiary"]["configuration"]["patterns"]) == 12


@pytest.mark.parametrize(
    "field",
    [
        name
        for name, rule in rules_by_field(GENERAL).items()
        if rule["configuration"]["strategy"] == "regex"
    ],
)
def test_general_patterns_preserve_original_regexes_in_order(field):
    patterns = rules_by_field(GENERAL)[field]["configuration"]["patterns"]
    assert [restore_captures(p) for p in patterns] == original_patterns(
        "base.py", f"_extract_{field}"
    )
    assert all(p.count("(?P<value>") == 1 for p in patterns)


def test_institution_override_sets():
    assert {code: set(rules_by_field(p)) for code, p in DEFAULTS.items()} == {
        "NUBANK": {"due_date", "payment_date", "source_institution"},
        "ITAU": {"authentication", "source_institution"},
        "CAIXA": {"source_institution"},
    }
    constants = {
        code: rules_by_field(p)["source_institution"]["configuration"]
        for code, p in DEFAULTS.items()
    }
    assert constants == {
        "NUBANK": {"strategy": "constant", "value": "Nubank"},
        "ITAU": {"strategy": "constant", "value": "Itaú"},
        "CAIXA": {"strategy": "constant", "value": "Caixa"},
    }


def test_institution_regex_overrides_preserve_original_regexes():
    nubank = rules_by_field(DEFAULTS["NUBANK"])
    for field in ("due_date", "payment_date"):
        configuration = nubank[field]["configuration"]
        assert configuration["parser"] == "date_month_name_pt_br"
        assert [restore_captures(p) for p in configuration["patterns"]] == (
            original_patterns("nubank.py", f"_extract_{field}")
        )
    assert nubank["due_date"]["configuration"]["normalization"] == "strip"
    assert nubank["payment_date"]["configuration"]["normalization"] == "ocr_day"
    itau = rules_by_field(DEFAULTS["ITAU"])["authentication"]["configuration"]
    assert [restore_captures(p) for p in itau["patterns"]] == original_patterns(
        "itau.py", "_extract_authentication"
    )


def test_seed_patterns_extract_expected_values():
    nubank = rules_by_field(DEFAULTS["NUBANK"])
    due = nubank["due_date"]["configuration"]["patterns"][0]
    assert re.search(due, "Vencimento 05 JAN 2025", re.I).group("value") == (
        "05 JAN 2025"
    )
    payment = nubank["payment_date"]["configuration"]["patterns"][0]
    assert re.search(payment, "NI FEV 2025 - 10:00:00", re.I).group("value") == (
        "NI FEV 2025"
    )
    general = rules_by_field(GENERAL)
    due = general["due_date"]["configuration"]["patterns"][2]
    assert re.search(due, "Vencimento 05/01/2025").group("value") == "05/01/2025"
