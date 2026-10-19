from dataclasses import dataclass
from collections.abc import Sequence
from uuid import UUID

from app.domain.category.schema import SubcategoryReconcileSchema


class CategoryReconciliationError(ValueError):
    """Raised when a requested child list violates aggregate invariants."""


@dataclass(frozen=True, slots=True)
class SubcategoryUpdate:
    id: UUID
    name: str
    icon: str | None
    color: str | None
    is_active: bool
    order: int


@dataclass(frozen=True, slots=True)
class SubcategoryCreate:
    name: str
    icon: str | None
    color: str | None
    is_active: bool
    order: int


@dataclass(frozen=True, slots=True)
class SubcategoryReconciliationPlan:
    updates: tuple[SubcategoryUpdate, ...]
    creates: tuple[SubcategoryCreate, ...]
    remove_ids: tuple[UUID, ...]


def build_subcategory_reconciliation_plan(
    subcategories: Sequence[SubcategoryReconcileSchema],
    existing_ids: Sequence[UUID],
) -> SubcategoryReconciliationPlan:
    """Validate the complete desired child list and return an ORM-free plan."""
    existing_id_set = set(existing_ids)
    if len(existing_id_set) != len(existing_ids):
        raise CategoryReconciliationError("Existing subcategory IDs are not unique")

    seen_ids: set[UUID] = set()
    seen_orders: set[int] = set()
    updates: list[SubcategoryUpdate] = []
    creates: list[SubcategoryCreate] = []

    for subcategory in subcategories:
        if subcategory.order in seen_orders:
            raise CategoryReconciliationError("Subcategory orders must be unique")
        seen_orders.add(subcategory.order)

        values = {
            "name": subcategory.name,
            "icon": subcategory.icon,
            "color": subcategory.color,
            "is_active": subcategory.is_active,
            "order": subcategory.order,
        }
        if subcategory.id is None:
            creates.append(SubcategoryCreate(**values))
            continue

        if subcategory.id in seen_ids:
            raise CategoryReconciliationError("Subcategory IDs must be unique")
        if subcategory.id not in existing_id_set:
            raise CategoryReconciliationError(
                "Subcategory ID is not a live child of this category"
            )
        seen_ids.add(subcategory.id)
        updates.append(SubcategoryUpdate(id=subcategory.id, **values))

    remove_ids = tuple(
        child_id for child_id in existing_ids if child_id not in seen_ids
    )
    return SubcategoryReconciliationPlan(
        updates=tuple(updates),
        creates=tuple(creates),
        remove_ids=remove_ids,
    )
