from app.domain.receipt.rules.enums import ProfileScope, ReceiptFieldName
from app.domain.receipt.rules.field.schema import ReceiptFieldRuleSchema
from app.domain.receipt.rules.schema import ReceiptRulesSchema


def merge_rules(
    rules: list[ReceiptRulesSchema], institution: str
) -> list[ReceiptFieldRuleSchema]:
    defaults: dict[ReceiptFieldName, ReceiptFieldRuleSchema] = {}
    overrides: dict[ReceiptFieldName, ReceiptFieldRuleSchema] = {}
    for profile in rules:
        if not profile.is_active or profile.deleted_at is not None:
            continue
        if profile.scope == ProfileScope.SYSTEM and profile.institution_code is None:
            target = defaults
        elif profile.institution_code == institution:
            target = overrides
        else:
            continue
        target.update(
            (rule.field_name, rule)
            for rule in profile.field_rules
            if rule.is_active and rule.deleted_at is None
        )
    return list((defaults | overrides).values())
