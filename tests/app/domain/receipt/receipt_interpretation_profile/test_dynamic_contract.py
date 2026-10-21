import pytest
from pydantic import ValidationError

from app.domain.receipt.receipt_interpretation_profile.schema import (
    ReceiptFieldRuleCreateSchema,
)
from tests.app.domain.receipt.receipt_interpretation_profile.test_schema import (
    field_payload,
)


def test_configuration_strategies_and_larger_pattern_collection():
    config = field_payload()
    config["configuration"]["patterns"] *= 20
    ReceiptFieldRuleCreateSchema.model_validate(config)
    ReceiptFieldRuleCreateSchema(
        field_name="source_institution",
        configuration={"strategy": "constant", "value": "Nubank"},
    )
    ReceiptFieldRuleCreateSchema(
        field_name="category", configuration={"strategy": "not_found"}
    )
    ReceiptFieldRuleCreateSchema.model_validate(
        field_payload("barcode", "text")
        | {
            "configuration": {
                "strategy": "regex",
                "patterns": ["(?P<value>[0-9 ]+)"],
                "parser": "text",
                "normalization": "remove_whitespace",
            }
        }
    )


@pytest.mark.parametrize(
    "field,configuration",
    [
        ("paid_amount", {"strategy": "constant", "value": "1"}),
        ("source_institution", {"strategy": "constant", "value": " "}),
        ("payer", {"strategy": "not_found", "code": "execute()"}),
        (
            "payer",
            {
                "strategy": "regex",
                "patterns": ["(?P<value>.)"],
                "parser": "text",
                "normalization": "ocr_day",
            },
        ),
        (
            "payer",
            {
                "strategy": "regex",
                "patterns": ["(?P<value>.)"],
                "parser": "text",
                "normalization": "remove_whitespace",
            },
        ),
        (
            "paid_amount",
            {
                "strategy": "regex",
                "patterns": ["(?P<value>.)"],
                "parser": "decimal_br",
                "fallback_field": "paid_amount",
            },
        ),
        (
            "effective_payer",
            {
                "strategy": "regex",
                "patterns": ["(?P<value>.)"],
                "parser": "text",
                "fallback_field": "paid_amount",
            },
        ),
        (
            "document_amount",
            {
                "strategy": "regex",
                "patterns": ["(?P<value>.)"],
                "parser": "decimal_br",
                "fallback_field": "document_amount",
            },
        ),
    ],
)
def test_non_allowlisted_behaviors_are_rejected(field, configuration):
    with pytest.raises(ValidationError):
        ReceiptFieldRuleCreateSchema(field_name=field, configuration=configuration)
