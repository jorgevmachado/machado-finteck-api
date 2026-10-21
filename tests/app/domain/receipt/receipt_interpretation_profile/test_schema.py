import json
import re
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import configure_mappers

from app.core.database import table_registry
from app.domain.receipt.data.schema import ReceiptData
from app.domain.receipt.receipt_interpretation_profile.business import (
    ProfileReconciliationError,
    build_reconciliation_plan,
)
from app.domain.receipt.receipt_interpretation_profile.enums import (
    DATE_FIELDS,
    MONEY_FIELDS,
    ReceiptFieldName,
)
from app.domain.receipt.receipt_interpretation_profile.schema import (
    ReceiptFieldRuleCreateSchema,
    ReceiptFieldRuleReconcileSchema,
    ReceiptIdentificationRuleReconcileSchema,
    ReceiptInterpretationProfileCreateSchema,
    ReceiptInterpretationProfileSchema,
    ReceiptInterpretationProfileUpdateSchema,
)
from app.models import ReceiptInterpretationProfile


def field_payload(field="paid_amount", parser="decimal_br"):
    return {
        "field_name": field,
        "configuration": {
            "strategy": "regex",
            "patterns": [r"Valor:\s*(?P<value>[\d.]+,\d{2})"],
            "parser": parser,
        },
    }


def test_models_and_schema_scope():
    configure_mappers()
    assert "receipt_interpretation_profiles" in table_registry.metadata.tables
    profile = ReceiptInterpretationProfile(
        user_id=None, name="Geral", institution_code=None
    )
    result = ReceiptInterpretationProfileSchema.model_validate(profile).model_dump()
    assert result["scope"] == "system"
    assert "user_id" not in result
    assert result["field_rules"] == []


def test_creation_defaults_normalization_and_fields_contract():
    profile = ReceiptInterpretationProfileCreateSchema(
        name="  Meu   Nubank  ", institution_code=" nubank "
    )
    assert profile.name == "Meu Nubank"
    assert profile.institution_code == "NUBANK"
    assert profile.is_active
    assert profile.field_rules == profile.identification_rules == []
    assert {field.value for field in ReceiptFieldName} == set(ReceiptData.model_fields)


@pytest.mark.parametrize("field", list(ReceiptFieldName))
def test_every_field_accepts_only_compatible_parsers(field):
    parser = (
        "decimal_br"
        if field in MONEY_FIELDS
        else "date_numeric_br"
        if field in DATE_FIELDS
        else "text"
    )
    ReceiptFieldRuleCreateSchema.model_validate(field_payload(field, parser))
    incompatible = "text" if parser != "text" else "decimal_br"
    with pytest.raises(ValidationError):
        ReceiptFieldRuleCreateSchema.model_validate(field_payload(field, incompatible))


@pytest.mark.parametrize(
    "patch",
    [
        {"name": " "},
        {"institution_code": " "},
        {"institution_code": "NU BANK"},
        {"institution_code": "A" * 65},
        {"user_id": str(uuid4())},
        {"scope": "system"},
        {"id": str(uuid4())},
        {"created_at": "2026-01-01"},
        {"is_active": "true"},
        {"identification_rules": None},
        {"field_rules": None},
        {"identification_rules": [{"pattern": "NU", "weight": 1}] * 101},
        {"field_rules": [field_payload()] * 2},
    ],
)
def test_invalid_profile_creation(patch):
    with pytest.raises(ValidationError):
        ReceiptInterpretationProfileCreateSchema.model_validate(
            {"name": "Nubank", "institution_code": "NUBANK"} | patch
        )


@pytest.mark.parametrize(
    "config",
    [
        {"patterns": []},
        {"patterns": ["(?P<value>"]},
        {"patterns": ["(value)"]},
        {"patterns": [" "]},
        {"patterns": ["a" * 2001]},
        {"patterns": ["(?P<value>x)"] * 21},
        {"parser": "python"},
        {"strategy": "script"},
        {"extra": "invalid"},
    ],
)
def test_invalid_configuration(config):
    payload = field_payload()
    payload["configuration"].update(config)
    with pytest.raises(ValidationError):
        ReceiptFieldRuleCreateSchema.model_validate(payload)


@pytest.mark.parametrize("weight", [True, 0, -1, "1", 1.2])
def test_identification_weight_is_strict(weight):
    with pytest.raises(ValidationError):
        ReceiptIdentificationRuleReconcileSchema(pattern="NU", weight=weight)


@pytest.mark.parametrize(
    "pattern", ["", " ", "[", "a" * 2001, "(" * 600, "x{999999999999999999}"]
)
def test_identification_pattern_is_validated(pattern):
    with pytest.raises(ValidationError):
        ReceiptIdentificationRuleReconcileSchema(pattern=pattern, weight=1)


def test_update_omission_null_and_managed_fields():
    assert ReceiptInterpretationProfileUpdateSchema().model_fields_set == set()
    assert ReceiptInterpretationProfileUpdateSchema(field_rules=[]).field_rules == []
    for field in ("name", "is_active", "field_rules", "identification_rules"):
        with pytest.raises(ValidationError):
            ReceiptInterpretationProfileUpdateSchema.model_validate({field: None})
    with pytest.raises(ValidationError):
        ReceiptInterpretationProfileUpdateSchema(institution_code="NUBANK")
    for schema, payload in (
        (ReceiptFieldRuleReconcileSchema, field_payload()),
        (ReceiptIdentificationRuleReconcileSchema, {"pattern": "NU", "weight": 1}),
    ):
        with pytest.raises(ValidationError):
            schema.model_validate(payload | {"id": None})


def test_reconciliation_mixed_empty_duplicates_and_unknown_ids():
    first, second = uuid4(), uuid4()
    retained = ReceiptFieldRuleReconcileSchema(id=first, **field_payload())
    new = ReceiptFieldRuleReconcileSchema(**field_payload("beneficiary", "text"))
    plan = build_reconciliation_plan([retained, new], [first, second])
    assert plan.remove_ids == (second,)
    assert plan.entries == (retained, new)
    assert build_reconciliation_plan([], [first, second]).remove_ids == (first, second)
    for entries, existing in (
        ([retained], []),
        ([retained, retained], [first]),
        ([new, new], []),
    ):
        with pytest.raises(ProfileReconciliationError):
            build_reconciliation_plan(entries, existing)


def test_reconciliation_allows_field_swaps_and_identification_updates():
    first, second = uuid4(), uuid4()
    swapped = [
        ReceiptFieldRuleReconcileSchema(id=first, **field_payload("payer", "text")),
        ReceiptFieldRuleReconcileSchema(
            id=second, **field_payload("beneficiary", "text")
        ),
    ]
    assert build_reconciliation_plan(swapped, [first, second]).remove_ids == ()
    identification = ReceiptIdentificationRuleReconcileSchema(
        id=first, pattern="NU", weight=100
    )
    assert build_reconciliation_plan([identification], [first]).entries == (
        identification,
    )


def test_readme_json_examples_validate_without_executing_patterns():
    readme = Path(
        "app/domain/receipt/receipt_interpretation_profile/README.md"
    ).read_text()
    examples = [
        json.loads(example)
        for example in re.findall(r"```json\n(.*?)\n```", readme, flags=re.DOTALL)
    ]
    assert len(examples) == 5
    ReceiptInterpretationProfileCreateSchema.model_validate(examples[0])
    for example in examples[1:]:
        update = ReceiptInterpretationProfileUpdateSchema.model_validate(example)
        if update.field_rules is not None:
            existing_ids = [
                child.id for child in update.field_rules if child.id is not None
            ]
            build_reconciliation_plan(update.field_rules, existing_ids)
