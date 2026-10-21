from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar
from uuid import UUID

from app.domain.receipt.receipt_interpretation_profile.schema import (
    ReceiptFieldRuleReconcileSchema,
    ReceiptIdentificationRuleReconcileSchema,
)

Rule = TypeVar(
    "Rule", ReceiptFieldRuleReconcileSchema, ReceiptIdentificationRuleReconcileSchema
)


class ProfileReconciliationError(ValueError):
    """The requested final child collection violates aggregate invariants."""


@dataclass(frozen=True)
class RuleReconciliationPlan(Generic[Rule]):
    entries: tuple[Rule, ...]
    remove_ids: tuple[UUID, ...]


def build_reconciliation_plan(
    entries: Sequence[Rule], existing_ids: Sequence[UUID]
) -> RuleReconciliationPlan[Rule]:
    existing = set(existing_ids)
    seen: set[UUID] = set()
    fields: set[str] = set()
    for entry in entries:
        if entry.id is not None:
            if entry.id in seen or entry.id not in existing:
                raise ProfileReconciliationError(
                    "Rule ID must identify a unique live child of this collection"
                )
            seen.add(entry.id)
        if isinstance(entry, ReceiptFieldRuleReconcileSchema):
            if entry.field_name in fields:
                raise ProfileReconciliationError("Field names must be unique")
            fields.add(entry.field_name)
    return RuleReconciliationPlan(
        entries=tuple(entries),
        remove_ids=tuple(child_id for child_id in existing_ids if child_id not in seen),
    )
