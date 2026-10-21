from uuid import uuid4

import pytest

from app.domain.receipt.rules.business import (
    ProfileReconciliationError,
    build_reconciliation_plan,
)
from app.domain.receipt.rules.field.schema import ReceiptFieldRuleReconcileSchema
from app.domain.receipt.rules.identification.schema import (
    ReceiptIdentificationRuleReconcileSchema,
)


@pytest.mark.parametrize("collection", ["fields", "identification"])
def test_reconciliation_updates_creates_and_removes(collection, rule_payload):
    first, second = uuid4(), uuid4()
    if collection == "fields":
        retained = ReceiptFieldRuleReconcileSchema(id=first, **rule_payload)
        new = ReceiptFieldRuleReconcileSchema(
            field_name="category", configuration={"strategy": "not_found"}
        )
    else:
        retained = ReceiptIdentificationRuleReconcileSchema(
            id=first, pattern="A", weight=2
        )
        new = ReceiptIdentificationRuleReconcileSchema(pattern="B", weight=3)
    plan = build_reconciliation_plan([retained, new], [first, second])
    assert plan.entries == (retained, new)
    assert plan.remove_ids == (second,)
    assert retained.id == first and new.id is None
    assert build_reconciliation_plan([], [first, second]).remove_ids == (first, second)
    for invalid in ([retained, retained],):
        with pytest.raises(ProfileReconciliationError):
            build_reconciliation_plan(invalid, [first, second])
    # Live IDs exclude foreign, deleted and other-collection children.
    with pytest.raises(ProfileReconciliationError):
        build_reconciliation_plan([retained], [second])


def test_final_membership_allows_swaps_and_replacement_but_not_duplicate_fields():
    first, second = uuid4(), uuid4()
    entries = [
        ReceiptFieldRuleReconcileSchema(
            id=first, field_name="beneficiary", configuration={"strategy": "not_found"}
        ),
        ReceiptFieldRuleReconcileSchema(
            id=second, field_name="payer", configuration={"strategy": "not_found"}
        ),
    ]
    assert build_reconciliation_plan(entries, [first, second]).remove_ids == ()
    replacement = entries[1].model_copy(update={"id": None})
    plan = build_reconciliation_plan([replacement], [second])
    assert plan.remove_ids == (second,)
    with pytest.raises(ProfileReconciliationError, match="unique"):
        build_reconciliation_plan(
            [entries[1], replacement.model_copy(update={"is_active": False})],
            [first, second],
        )
