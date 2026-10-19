from uuid import uuid4

import pytest

from app.domain.category.business import (
    CategoryReconciliationError,
    SubcategoryCreate,
    SubcategoryUpdate,
    build_subcategory_reconciliation_plan,
)
from app.domain.category.schema import SubcategoryReconcileSchema


def _child(name, order, *, child_id=None, **kwargs):
    return SubcategoryReconcileSchema(
        name=name,
        order=order,
        **({"id": child_id} if child_id is not None else {}),
        **kwargs,
    )


def test_plan_reconciles_retained_new_and_omitted_children():
    retained_id = uuid4()
    removed_id = uuid4()
    existing_ids = [retained_id, removed_id]

    plan = build_subcategory_reconciliation_plan(
        [
            _child("Updated", 2, child_id=retained_id, is_active=False),
            _child("New", 1, color="#aB123F"),
        ],
        existing_ids,
    )

    assert plan.updates == (
        SubcategoryUpdate(
            id=retained_id,
            name="Updated",
            icon=None,
            color=None,
            is_active=False,
            order=2,
        ),
    )
    assert plan.creates == (
        SubcategoryCreate(
            name="New",
            icon=None,
            color="#aB123F",
            is_active=True,
            order=1,
        ),
    )
    assert plan.remove_ids == (removed_id,)


def test_plan_accepts_order_swaps_and_gaps_without_mutating_inputs():
    first_id = uuid4()
    second_id = uuid4()
    first = _child("First", 2, child_id=first_id)
    second = _child("Second", 5, child_id=second_id)

    plan = build_subcategory_reconciliation_plan(
        [first, second],
        [first_id, second_id],
    )

    assert [(item.id, item.order) for item in plan.updates] == [
        (first_id, 2),
        (second_id, 5),
    ]
    assert plan.creates == ()
    assert plan.remove_ids == ()
    assert first.order == 2
    assert second.order == 5


def test_empty_complete_list_removes_all_existing_children():
    existing_ids = [uuid4(), uuid4()]

    plan = build_subcategory_reconciliation_plan([], existing_ids)

    assert plan.updates == ()
    assert plan.creates == ()
    assert plan.remove_ids == tuple(existing_ids)


def test_empty_list_for_aggregate_without_children_is_valid():
    plan = build_subcategory_reconciliation_plan([], [])

    assert plan.remove_ids == ()


@pytest.mark.parametrize(
    "children",
    [
        lambda child_id: [
            _child("First", 1, child_id=child_id),
            _child("Again", 2, child_id=child_id),
        ],
        lambda child_id: [
            _child("First", 1, child_id=child_id),
            _child("New", 2, child_id=child_id),
        ],
    ],
)
def test_plan_rejects_duplicate_existing_ids(children):
    child_id = uuid4()

    with pytest.raises(CategoryReconciliationError, match="IDs must be unique"):
        build_subcategory_reconciliation_plan(children(child_id), [child_id])


def test_plan_rejects_duplicate_orders_even_for_inactive_children():
    first_id = uuid4()
    second_id = uuid4()

    with pytest.raises(CategoryReconciliationError, match="orders must be unique"):
        build_subcategory_reconciliation_plan(
            [
                _child("Inactive", 1, child_id=first_id, is_active=False),
                _child("Active", 1, child_id=second_id),
            ],
            [first_id, second_id],
        )


@pytest.mark.parametrize("child_id_kind", ["unknown", "deleted_or_foreign"])
def test_plan_rejects_ids_not_in_the_live_children(child_id_kind):
    if child_id_kind == "unknown":
        existing_ids = []
    else:
        existing_ids = [uuid4()]
    invalid_id = uuid4()

    with pytest.raises(CategoryReconciliationError, match="not a live child"):
        build_subcategory_reconciliation_plan(
            [_child("Unknown", 1, child_id=invalid_id)],
            existing_ids,
        )


def test_plan_rejects_duplicate_orders_for_new_children():
    with pytest.raises(CategoryReconciliationError, match="orders must be unique"):
        build_subcategory_reconciliation_plan(
            [_child("First", 1), _child("Second", 1)],
            [],
        )


def test_plan_rejects_duplicate_ids_in_persisted_children():
    child_id = uuid4()

    with pytest.raises(CategoryReconciliationError, match="Existing.*not unique"):
        build_subcategory_reconciliation_plan([], [child_id, child_id])
