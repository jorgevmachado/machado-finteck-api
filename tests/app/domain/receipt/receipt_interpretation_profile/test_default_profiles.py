import json
from pathlib import Path

from app.domain.receipt.interpretation.institutions.rules.rules import (
    INSTITUTION_RULES,
)
from app.domain.receipt.receipt_interpretation_profile.schema import (
    ReceiptInterpretationProfileCreateSchema,
)


def test_seed_profiles_are_valid_and_preserve_existing_identification_rules():
    path = Path(
        "app/domain/receipt/receipt_interpretation_profile/default_profiles.json"
    )
    profiles = [
        ReceiptInterpretationProfileCreateSchema.model_validate(item)
        for item in json.loads(path.read_text(encoding="utf-8"))
    ]
    codes = [profile.institution_code for profile in profiles]
    expected_codes = {rule.institution.value.upper() for rule in INSTITUTION_RULES}
    assert len(codes) == len(set(codes))
    assert set(codes) == expected_codes
    for profile in profiles:
        expected = [
            (rule.pattern, rule.weight)
            for rule in INSTITUTION_RULES
            if rule.institution.value.upper() == profile.institution_code
        ]
        assert [
            (rule.pattern, rule.weight) for rule in profile.identification_rules
        ] == expected
        assert profile.is_active
        assert all(rule.is_active for rule in profile.identification_rules)
        assert profile.field_rules
