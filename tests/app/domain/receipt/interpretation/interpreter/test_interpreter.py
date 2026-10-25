import subprocess
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.domain.receipt.data.enums import DataStatusEnum
from app.domain.receipt.interpretation import Interpretation
from app.domain.receipt.interpretation.interpreter.interpreter import (
    Interpreter,
    InterpreterRequest,
)
from app.domain.receipt.rules.defaults import load_default_receipt_rules
from app.domain.receipt.rules.field.schema import ReceiptFieldRuleSchema
from app.domain.receipt.rules.schema import ReceiptRulesSchema
from app.domain.receipt.rules.service import ReceiptRulesService
from app.models import ReceiptFieldRule

MODULE = "app.domain.receipt.interpretation.interpreter.interpreter"


@pytest.fixture
def profiles():
    return [
        ReceiptRulesSchema.model_validate(
            ReceiptRulesService._build_aggregate(
                None if payload.institution_code is None else uuid4(), payload
            )
        )
        for payload in load_default_receipt_rules()
    ]


def rule(field_name, configuration):
    return ReceiptFieldRuleSchema.model_validate(
        ReceiptFieldRule(
            profile_id=uuid4(), field_name=field_name, configuration=configuration
        )
    )


def regex(field_name, pattern, parser="text", **options):
    return rule(
        field_name,
        {
            "strategy": "regex",
            "patterns": [pattern],
            "parser": parser,
            **options,
        },
    )


def test_extracts_receipt_attributes_and_applies_configured_fallbacks(profiles):
    text = (
        "Multa: R$ 1,20\n"
        "Nome do pagador: Maria\n"
        "C\u00f3digo de barras: 123 456\n"
        "Vencimento 28/10/2026\n"
        "Desconto: R$ 2,00\n"
        "Juros/Mora: R$ 0,50\n"
        "Valor pago: R$ 1.234,56\n"
        "Nome do benefici\u00e1rio: Empresa\n"
        "Data do pagamento: 25/10/2026\n"
        "Total de encargos: R$ 1,70\n"
        "Autentica\u00e7\u00e3o: ABC123\n"
        "ID da transa\u00e7\u00e3o: TX-123\n"
        "Institui\u00e7\u00e3o Emissora: 001 - Banco Destino\n"
    )
    data = Interpreter(profiles, "ITAU").interpret(text)
    expected = {
        "fine": Decimal("1.20"),
        "payer": "Maria",
        "barcode": "123456",
        "due_date": date(2026, 10, 28),
        "discount": Decimal("2.00"),
        "interest": Decimal("0.50"),
        "paid_amount": Decimal("1234.56"),
        "beneficiary": "Empresa",
        "payment_date": date(2026, 10, 25),
        "total_charges": Decimal("1.70"),
        "authentication": "ABC123",
        "transaction_id": "TX-123",
        "effective_payer": "Maria",
        "document_amount": Decimal("1234.56"),
        "source_institution": "Ita\u00fa",
        "destination_institution": "Banco Destino",
    }
    for name, value in expected.items():
        field = getattr(data, name)
        assert field.value == value, name
        assert type(field.value) is type(value), name
        assert field.status == DataStatusEnum.FOUND, name
    for name in ("category", "description"):
        assert getattr(data, name).value is None
        assert getattr(data, name).status == DataStatusEnum.NOT_FOUND


def test_missing_rules_return_complete_not_found_data():
    data = Interpreter([], "unknow").interpret("")
    assert all(
        field["value"] is None and field["status"] == DataStatusEnum.NOT_FOUND
        for field in data.model_dump().values()
    )


@pytest.mark.parametrize(
    "value,parser,normalization,expected",
    [
        ("25/10/2026", "date_numeric_br", "strip", date(2026, 10, 25)),
        ("31/02/2026", "date_numeric_br", "strip", None),
        ("25 out 2026", "date_month_name_pt_br", "strip", date(2026, 10, 25)),
        ("NI OUT 2026", "date_month_name_pt_br", "ocr_day", date(2026, 10, 11)),
        ("IL out 2026", "date_month_name_pt_br", "ocr_day", date(2026, 10, 11)),
        ("31 FEV 2026", "date_month_name_pt_br", "strip", None),
        ("25 XYZ 2026", "date_month_name_pt_br", "strip", None),
        ("invalid", "date_month_name_pt_br", "strip", None),
    ],
)
def test_date_parsers_validate_calendar_and_normalize_ocr(
    value, parser, normalization, expected
):
    field_rule = regex(
        "payment_date", r"(?P<value>.+)", parser, normalization=normalization
    )
    data = Interpreter._interpret(
        InterpreterRequest(text=value, institution="unknow", rules=[field_rule])
    )
    assert data.payment_date.value == expected
    assert data.payment_date.status == (
        DataStatusEnum.FOUND if expected else DataStatusEnum.AMBIGUOUS
    )


@pytest.mark.parametrize("value", ["invalid", "NaN", "Infinity", ""])
def test_invalid_money_is_ambiguous_without_affecting_other_fields(value):
    rules = [
        regex("paid_amount", r"Valor: (?P<value>[^\n]*)", "decimal_br"),
        regex("payer", r"Nome: (?P<value>[^\n]+)"),
    ]
    data = Interpreter._interpret(
        InterpreterRequest(
            text=f"Valor: {value}\nNome: Maria", institution="unknow", rules=rules
        )
    )
    assert data.paid_amount.value is None
    assert data.paid_amount.status == DataStatusEnum.AMBIGUOUS
    assert data.payer.value == "Maria"


def test_pattern_priority_empty_groups_and_custom_text_fields():
    description = regex("description", r"(?P<value>missing)")
    description.configuration.patterns.extend(
        [r"Description: (?P<value>[^\n]+)", r"Other: (?P<value>[^\n]+)"]
    )
    rules = [
        description,
        regex("category", r"Category: (?P<value>[^\n]+)"),
        regex("payer", r"Empty:(?P<value>[ ]*)"),
        regex("beneficiary", r"Optional:(?P<value>x)?"),
    ]
    data = Interpreter._interpret(
        InterpreterRequest(
            text="Description:  Purchase  \nOther: ignored\nCategory: Bills\nEmpty:  \nOptional:",
            institution="unknow",
            rules=rules,
        )
    )
    assert data.description.value == "Purchase"
    assert data.category.value == "Bills"
    assert data.payer.status == DataStatusEnum.AMBIGUOUS
    assert data.beneficiary.status == DataStatusEnum.AMBIGUOUS


@pytest.mark.parametrize("own_value", [None, "", "Other"])
def test_fallbacks_are_order_independent_and_do_not_replace_found_values(own_value):
    rules = [
        regex("effective_payer", r"Efetivo: (?P<value>[^\n]*)", fallback_field="payer"),
        regex("payer", r"Nome: (?P<value>[^\n]+)"),
    ]
    text = "Nome: Maria"
    if own_value is not None:
        text += f"\nEfetivo: {own_value}"
    data = Interpreter._interpret(
        InterpreterRequest(text=text, institution="unknow", rules=rules)
    )
    assert data.effective_payer.value == (own_value or "Maria")
    assert data.effective_payer.status == DataStatusEnum.FOUND


@pytest.mark.parametrize(
    "configuration,text,expected",
    [
        ({"strategy": "constant", "value": "Bank"}, "", "Bank"),
        ({"strategy": "not_found"}, "Banco", None),
        (
            {
                "strategy": "source",
                "identified_value": "Identified",
                "matches": [{"contains": "brand", "value": "Mapped"}],
            },
            "BRAND",
            "Mapped",
        ),
        (
            {
                "strategy": "source",
                "identified_value": "Identified",
                "extraction": {
                    "strategy": "regex",
                    "parser": "text",
                    "patterns": [r"Banco: (?P<value>.+)"],
                },
                "mappings": [{"contains": "legacy", "value": "Mapped"}],
            },
            "Banco: legacy name",
            "Mapped",
        ),
    ],
)
def test_source_institution_reuses_existing_strategies(configuration, text, expected):
    data = Interpreter._interpret(
        InterpreterRequest(
            text=text,
            institution="unknow",
            rules=[rule("source_institution", configuration)],
        )
    )
    assert data.source_institution.value == expected
    assert data.source_institution.status == (
        DataStatusEnum.FOUND if expected else DataStatusEnum.NOT_FOUND
    )


def test_interpretation_returns_data_and_required_field_validation(profiles):
    result = Interpretation(
        profiles,
        "ITAU UNIBANCO\nValor pago: R$ 42,00\n"
        "Data do pagamento: 25/10/2026\nNome do benefici\u00e1rio: Empresa\n",
    ).result()
    assert result.errors == []
    assert result.data.paid_amount.value == Decimal("42.00")
    assert result.data.source_institution.value == "Ita\u00fa"
    missing = Interpretation(profiles, "").result()
    assert {error.field for error in missing.errors} == {
        "payment_date",
        "paid_amount",
        "beneficiary",
        "source_institution",
    }


@pytest.mark.parametrize(
    "error",
    [
        OSError("cannot start"),
        subprocess.TimeoutExpired("interpreter", 3),
        subprocess.CalledProcessError(1, "interpreter"),
    ],
)
def test_execution_failure_returns_ambiguous_fields_and_logs(error, caplog):
    with patch(f"{MODULE}.subprocess.run", side_effect=error):
        data = Interpreter([], "unknow").interpret("text")
    assert all(
        field["status"] == DataStatusEnum.AMBIGUOUS
        for field in data.model_dump().values()
    )
    assert caplog.records


def test_invalid_worker_output_is_logged_and_does_not_raise(caplog):
    with patch(
        f"{MODULE}.subprocess.run", return_value=SimpleNamespace(stdout=b"invalid")
    ):
        data = Interpreter([], "unknow").interpret("")
    assert data.payer.status == DataStatusEnum.AMBIGUOUS
    assert caplog.records


def test_text_limit_is_checked_before_spawning_worker(caplog):
    with patch(f"{MODULE}.subprocess.run") as run:
        data = Interpreter([], "unknow").interpret("x" * 1_000_001)
    run.assert_not_called()
    assert data.payer.status == DataStatusEnum.AMBIGUOUS
    assert caplog.records


def test_missing_fallback_preserves_original_field_status():
    rules = [
        regex("effective_payer", r"Efetivo: (?P<value>[^\n]*)", fallback_field="payer"),
        regex(
            "document_amount",
            r"Documento: (?P<value>.+)",
            "decimal_br",
            fallback_field="paid_amount",
        ),
    ]
    data = Interpreter._interpret(
        InterpreterRequest(text="Efetivo: ", institution="unknow", rules=rules)
    )
    assert data.effective_payer.value is None
    assert data.effective_payer.status == DataStatusEnum.AMBIGUOUS
    assert data.document_amount.value is None
    assert data.document_amount.status == DataStatusEnum.NOT_FOUND


def test_direct_extraction_handles_not_found_decimal_and_barcode_normalization():
    data = Interpreter._interpret(
        InterpreterRequest(
            text="Valor: 1.234,56\nBarcode: 123 456\n",
            institution="unknow",
            rules=[
                rule("category", {"strategy": "not_found"}),
                regex("paid_amount", r"Valor: (?P<value>.+)", "decimal_br"),
                regex(
                    "barcode",
                    r"Barcode: (?P<value>.+)",
                    normalization="remove_whitespace",
                ),
            ],
        )
    )
    assert data.category.status == DataStatusEnum.NOT_FOUND
    assert data.paid_amount.value == Decimal("1234.56")
    assert data.paid_amount.status == DataStatusEnum.FOUND
    assert data.barcode.value == "123456"


def test_worker_filters_inactive_and_deleted_rules():
    from app.models import utcnow

    inactive = regex("payer", r"(?P<value>.+)")
    inactive.is_active = False
    deleted = regex("beneficiary", r"(?P<value>.+)")
    deleted.deleted_at = utcnow()
    data = Interpreter._interpret(
        InterpreterRequest(
            text="Maria", institution="unknow", rules=[inactive, deleted]
        )
    )
    assert data.payer.status == DataStatusEnum.NOT_FOUND
    assert data.beneficiary.status == DataStatusEnum.NOT_FOUND


def test_interpreter_worker_limits_resources_and_serializes_typed_data(monkeypatch):
    from io import StringIO
    from runpy import run_path

    import resource

    from app.domain.receipt.data.schema import ReceiptData
    from app.domain.receipt.interpretation.interpreter import interpreter

    request = InterpreterRequest(
        text="Valor: 42,50",
        institution="unknow",
        rules=[regex("paid_amount", r"Valor: (?P<value>.+)", "decimal_br")],
    )
    output = StringIO()
    monkeypatch.setattr(interpreter.sys, "stdin", StringIO(request.model_dump_json()))
    monkeypatch.setattr(interpreter.sys, "stdout", output)
    with patch.object(resource, "setrlimit") as limits:
        run_path(interpreter.__file__, run_name="__main__")
    data = ReceiptData.model_validate_json(output.getvalue())
    assert data.paid_amount.value == Decimal("42.50")
    assert data.paid_amount.status == DataStatusEnum.FOUND
    limits.assert_any_call(resource.RLIMIT_CPU, (2, 2))
    limits.assert_any_call(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
