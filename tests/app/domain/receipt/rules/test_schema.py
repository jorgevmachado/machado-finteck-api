from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.receipt.rules.configuration.schema import ReceiptFieldConfiguration
from app.domain.receipt.rules.enums import DATE_FIELDS, MONEY_FIELDS, ReceiptFieldName
from app.domain.receipt.rules.field.schema import (
    ReceiptFieldRuleCreateSchema,
    ReceiptFieldRuleReconcileSchema,
)
from app.domain.receipt.rules.identification.schema import (
    ReceiptIdentificationRuleCreateSchema,
    ReceiptIdentificationRuleReconcileSchema,
)
from app.domain.receipt.rules.schema import (
    ReceiptRulesCreateSchema,
    ReceiptRulesFilter,
    ReceiptRulesSchema,
    ReceiptRulesUpdateSchema,
)
from app.models import ReceiptFieldRule, utcnow


def test_create_normalizes_identity_and_preserves_omission_defaults():
    result = ReceiptRulesCreateSchema(
        name="  Meu  Banco  ", institution_code=" bank-1 "
    )
    assert result.name == "Meu Banco"
    assert result.institution_code == "BANK-1"
    assert result.is_active
    assert result.field_rules == result.identification_rules == []


@pytest.mark.parametrize(
    "patch",
    [
        {"name": " "},
        {"name": None},
        {"institution_code": None},
        {"institution_code": ""},
        {"institution_code": "BAN CO"},
        {"institution_code": "-BANK"},
        {"institution_code": "A" * 65},
        {"user_id": str(uuid4())},
        {"id": str(uuid4())},
        {"is_active": "true"},
        {"field_rules": None},
        {"identification_rules": None},
        {
            "field_rules": [
                {"field_name": "category", "configuration": {"strategy": "not_found"}}
            ]
            * 101
        },
        {"identification_rules": [{"pattern": "BANK", "weight": 1}] * 101},
    ],
)
def test_create_rejects_invalid_identity_managed_fields_and_limits(patch):
    with pytest.raises(ValidationError):
        ReceiptRulesCreateSchema.model_validate(
            {"name": "Bank", "institution_code": "BANK"} | patch
        )


def test_create_rejects_duplicate_fields_even_if_inactive(rule_payload):
    with pytest.raises(ValidationError, match="unique"):
        ReceiptRulesCreateSchema(
            name="Bank",
            institution_code="BANK",
            field_rules=[rule_payload, rule_payload | {"is_active": False}],
        )


@pytest.mark.parametrize("field", list(ReceiptFieldName))
def test_all_field_types_require_compatible_parsers(field):
    parser = (
        "decimal_br"
        if field in MONEY_FIELDS
        else "date_numeric_br"
        if field in DATE_FIELDS
        else "text"
    )
    configuration = {
        "strategy": "regex",
        "patterns": ["(?P<value>x)"],
        "parser": parser,
    }
    ReceiptFieldRuleCreateSchema(field_name=field, configuration=configuration)
    configuration["parser"] = "text" if parser != "text" else "decimal_br"
    with pytest.raises(ValidationError):
        ReceiptFieldRuleCreateSchema(field_name=field, configuration=configuration)
    ReceiptFieldRuleCreateSchema(
        field_name=field, configuration={"strategy": "not_found"}
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"patterns": []},
        {"patterns": ["(?P<value>x)"] * 21},
        {"patterns": ["a" * 2001]},
        {"patterns": [" "]},
        {"patterns": ["["]},
        {"patterns": ["(value)"]},
        {"patterns": ["(" * 600]},
        {"patterns": ["x{99999999999999}"]},
        {"parser": "eval"},
        {"strategy": "script"},
        {"extra": True},
    ],
)
def test_regex_configuration_rejects_unsupported_or_invalid_values(patch):
    with pytest.raises(ValidationError):
        ReceiptFieldConfiguration.model_validate(
            {"strategy": "regex", "patterns": ["(?P<value>x)"], "parser": "text"}
            | patch
        )


def test_normalizations_and_fallbacks_are_allowlisted(rule_payload):
    cases = [
        ("barcode", "text", "remove_whitespace", None),
        ("payment_date", "date_month_name_pt_br", "ocr_day", None),
        ("effective_payer", "text", "strip", "payer"),
        ("document_amount", "decimal_br", "strip", "paid_amount"),
    ]
    for name, parser, normalization, fallback in cases:
        ReceiptFieldRuleCreateSchema(
            field_name=name,
            configuration={
                "strategy": "regex",
                "patterns": ["(?P<value>x)"],
                "parser": parser,
                "normalization": normalization,
                "fallback_field": fallback,
            },
        )
    for patch in (
        {"normalization": "remove_whitespace"},
        {"normalization": "ocr_day"},
        {"fallback_field": "paid_amount"},
    ):
        with pytest.raises(ValidationError):
            ReceiptFieldRuleCreateSchema(
                field_name="payer",
                configuration=rule_payload["configuration"] | patch,
            )


def test_constants_validate_and_are_limited_to_source():
    rule = ReceiptFieldRuleCreateSchema(
        field_name="source_institution",
        configuration={"strategy": "constant", "value": "  Banco  "},
    )
    assert rule.configuration.value == "Banco"
    for field, value in (("payer", "Banco"), ("source_institution", " ")):
        with pytest.raises(ValidationError):
            ReceiptFieldRuleCreateSchema(
                field_name=field, configuration={"strategy": "constant", "value": value}
            )


@pytest.mark.parametrize("weight", [True, False, 0, -1, "1", 1.5])
def test_identification_weight_is_strict_positive_integer(weight):
    with pytest.raises(ValidationError):
        ReceiptIdentificationRuleCreateSchema(pattern="BANK", weight=weight)


@pytest.mark.parametrize("pattern", ["", " ", "[", "x" * 2001])
def test_identification_requires_valid_pattern(pattern):
    with pytest.raises(ValidationError):
        ReceiptIdentificationRuleCreateSchema(pattern=pattern, weight=1)


def test_update_omission_null_managed_identity_and_child_ids(rule_payload):
    assert ReceiptRulesUpdateSchema().model_fields_set == set()
    result = ReceiptRulesUpdateSchema(field_rules=[])
    assert result.field_rules == []
    assert result.identification_rules is None
    for field in ("name", "is_active", "field_rules", "identification_rules"):
        with pytest.raises(ValidationError):
            ReceiptRulesUpdateSchema.model_validate({field: None})
    for field in ("institution_code", "user_id", "id"):
        with pytest.raises(ValidationError):
            ReceiptRulesUpdateSchema.model_validate({field: str(uuid4())})
    for schema, payload in (
        (ReceiptFieldRuleReconcileSchema, rule_payload),
        (ReceiptIdentificationRuleReconcileSchema, {"pattern": "BANK", "weight": 1}),
    ):
        assert schema.model_validate(payload).id is None
        assert schema.model_validate(payload | {"id": uuid4()}).id is not None
        with pytest.raises(ValidationError):
            schema.model_validate(payload | {"id": None})
    for schema, payload in (
        (ReceiptFieldRuleCreateSchema, rule_payload),
        (ReceiptIdentificationRuleCreateSchema, {"pattern": "BANK", "weight": 1}),
    ):
        with pytest.raises(ValidationError):
            schema.model_validate(payload | {"id": str(uuid4())})


def test_response_derives_scope_filters_deleted_children_and_orders(
    profile, rule_payload
):
    removed = ReceiptFieldRule(profile_id=profile.id, **rule_payload)
    removed.deleted_at = utcnow()
    profile.field_rules.append(removed)
    response = ReceiptRulesSchema.model_validate(profile)
    assert response.scope == "private"
    assert len(response.field_rules) == 1
    serialized = response.model_dump(mode="json")
    assert "user_id" not in serialized
    assert "profile_id" not in serialized["field_rules"][0]
    assert ReceiptRulesSchema.model_validate(serialized) == response
    profile.user_id = None
    profile.institution_code = None
    assert ReceiptRulesSchema.model_validate(profile).scope == "system"


@pytest.mark.parametrize(
    "patch", [{"page": -1}, {"offset": -1}, {"limit": 0}, {"scope": "admin"}]
)
def test_filter_rejects_invalid_pagination_and_scope(patch):
    with pytest.raises(ValidationError):
        ReceiptRulesFilter.model_validate(patch)
