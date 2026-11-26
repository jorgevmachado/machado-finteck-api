from datetime import date

import pytest

from app.domain.transaction.statement.business import (
    occurrence_index_at,
    shift_occurrences_back,
)
from app.domain.transaction.statement.schema import StatementSeriesSchema
from app.models import TransactionFrequencyUnitEnum


def _series(**kwargs):
    payload = {
        "kind": "CLOSED",
        "name": "Notebook",
        "value": "500.00",
        "direction": "OUT",
        "account_id": "6f1c1c3f-0f9b-4f1c-9b6c-2a1f0c9d8e7a",
        "start_date": "2025-09-13",
        "frequency_unit": "MONTH",
        "frequency_interval": 1,
        "day_of_month": 13,
        "installments": 10,
        "id": "11111111-1111-4111-8111-111111111111",
        "account": {
            "id": "6f1c1c3f-0f9b-4f1c-9b6c-2a1f0c9d8e7a",
            "name": "Main",
            "type": "CHECKING",
            "is_active": True,
            "created_at": "2025-01-01T00:00:00Z",
        },
        "note": None,
        "end_date": None,
        "created_at": "2025-01-01T00:00:00Z",
        **kwargs,
    }
    return StatementSeriesSchema.model_validate(payload)


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (date(2025, 9, 13), 1),
        (date(2025, 10, 13), 2),
        (date(2025, 11, 13), 3),
        (date(2026, 6, 13), 10),
    ],
)
def test_occurrence_index_matches_the_projected_position(target, expected):
    assert occurrence_index_at(_series(), target) == expected


@pytest.mark.parametrize(
    "target",
    [
        date(2025, 8, 13),  # before the plan starts
        date(2025, 11, 14),  # wrong day of the month
        date(2026, 7, 13),  # past the last installment
    ],
)
def test_occurrence_index_rejects_dates_outside_the_plan(target):
    assert occurrence_index_at(_series(), target) is None


def test_occurrence_index_ignores_the_end_of_an_open_series():
    series = _series(kind="OPEN", installments=None)

    assert occurrence_index_at(series, date(2030, 1, 13)) == 53


def test_shift_back_derives_the_start_of_a_mid_plan_installment():
    assert shift_occurrences_back(
        date(2025, 11, 13),
        steps=2,
        unit=TransactionFrequencyUnitEnum.MONTH,
        interval=1,
    ) == date(2025, 9, 13)


def test_shift_back_clamps_the_day_to_the_shorter_month():
    assert shift_occurrences_back(
        date(2025, 3, 31),
        steps=1,
        unit=TransactionFrequencyUnitEnum.MONTH,
        interval=1,
    ) == date(2025, 2, 28)


def test_shift_back_returns_the_target_when_there_is_nothing_to_shift():
    target = date(2025, 11, 13)

    assert (
        shift_occurrences_back(
            target, steps=0, unit=TransactionFrequencyUnitEnum.MONTH, interval=1
        )
        == target
    )


def test_shift_back_handles_weekly_plans():
    assert shift_occurrences_back(
        date(2025, 11, 13),
        steps=2,
        unit=TransactionFrequencyUnitEnum.WEEK,
        interval=1,
    ) == date(2025, 10, 30)


def test_shift_back_then_index_round_trips_to_the_original_position():
    target = date(2025, 11, 13)
    start = shift_occurrences_back(
        target, steps=2, unit=TransactionFrequencyUnitEnum.MONTH, interval=1
    )
    series = _series(start_date=start.isoformat())

    assert occurrence_index_at(series, target) == 3
