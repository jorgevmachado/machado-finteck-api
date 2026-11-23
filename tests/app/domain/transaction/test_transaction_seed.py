from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from freezegun import freeze_time
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.database.base import table_registry
from app.domain.transaction.business import _shift_month, build_transaction_seed
from app.domain.transaction.repository import TransactionRepository
from app.domain.transaction.scheduled.service import ScheduledTransactionService
from app.domain.transaction.schema import TransactionSeedRequestSchema
from app.domain.transaction.seeds import (
    InstallmentPlanSeedTemplate,
    RecurrenceSeedTemplate,
    load_seeds_installment_plans,
    load_seeds_recurrences,
    load_seeds_transactions,
)
from app.domain.transaction.series.service import TransactionSeriesService
from app.domain.transaction.service import TransactionService
from app.models import (
    Account,
    AccountTypeEnum,
    CreditCard,
    CreditCardBrandEnum,
    ScheduledTransaction,
    Transaction,
    TransactionDirectionEnum,
    TransactionFrequencyUnitEnum,
    TransactionKindEnum,
    TransactionSeries,
    TransactionStatusEnum,
)


@pytest.fixture
def admin(user):
    user.role = SimpleNamespace(name_code="admin", deleted_at=None)
    return user


def build_plan(**overrides):
    arguments = {
        "payload": TransactionSeedRequestSchema(),
        "seed": 42,
        "today": date(2026, 11, 4),
        "templates": load_seeds_transactions(),
        "recurrence_templates": load_seeds_recurrences(),
        "installment_templates": load_seeds_installment_plans(),
        "account_ids": [UUID(int=1)],
        "credit_card_ids": [UUID(int=2)],
        "subcategories": {"Supermercado": UUID(int=3)},
    }
    return build_transaction_seed(**(arguments | overrides))


def test_seed_plan_rejects_missing_accounts():
    with pytest.raises(ValueError, match="At least one account is required"):
        build_plan(account_ids=[])


@pytest.mark.parametrize("direction", ["IN", "OUT"])
def test_transaction_catalog_requires_both_directions(monkeypatch, direction):
    catalog = (
        '[{"name": "Only one direction", "direction": "'
        + direction
        + '", "valueRange": {"min": 1, "max": 2}, "weight": 1}]'
    )
    monkeypatch.setattr(
        "app.domain.transaction.seeds.Path.read_text",
        lambda *args, **kwargs: catalog,
    )
    with pytest.raises(ValueError, match="must contain IN and OUT templates"):
        load_seeds_transactions()


@pytest.mark.parametrize(
    "values",
    [
        {"transactions": 0, "recurrences": 0, "installment_plans": 0},
        {"transactions": -1},
        {"transactions": 1001},
        {"recurrences": 101},
        {"installment_plans": 101},
        {"months": 0},
        {"months": 25},
        {"seed": -1},
        {"seed": 2**32},
        {"transactions": True},
        {"months": 1.5},
        {"seed": "42"},
        {"user_id": str(uuid4())},
    ],
)
def test_seed_rejects_invalid_requests(values):
    with pytest.raises(ValidationError):
        TransactionSeedRequestSchema(**values)


def test_plan_is_reproducible_and_matches_catalog_and_period():
    plan = build_plan()
    assert plan == build_plan()
    assert plan != build_plan(seed=43)
    assert plan.start_date == date(2026, 6, 1)
    assert plan.end_date == date(2026, 11, 30)
    assert len(plan.transactions) == 100
    assert (
        sum(item.direction == TransactionDirectionEnum.IN for item in plan.transactions)
        == 15
    )
    assert len(plan.series) == 10
    templates = {item.name: item for item in load_seeds_transactions()}
    for item in plan.transactions:
        template = templates[item.name]
        assert template.value_range.min <= item.value <= template.value_range.max
        assert item.value == item.value.quantize(Decimal("0.01"))
        assert plan.start_date <= item.expected_on <= plan.end_date
        assert item.account_id == UUID(int=1)
        assert item.subcategory_id == (
            UUID(int=3) if template.category_hint == "Supermercado" else None
        )
        if item.direction == TransactionDirectionEnum.IN:
            assert item.credit_card_id is None
        if item.expected_on < date(2026, 11, 4):
            assert item.status == TransactionStatusEnum.SETTLED
            assert item.settled_on == item.expected_on
        else:
            assert item.status == TransactionStatusEnum.PENDING
            assert item.settled_on is None
    assert any(item.credit_card_id for item in plan.transactions)


def test_series_use_separate_catalogs_and_materialize_consistent_occurrences():
    plan = build_plan(credit_card_ids=[], subcategories={})
    recurrences = {item.name: item for item in load_seeds_recurrences()}
    installments = {item.name: item for item in load_seeds_installment_plans()}
    for index, item in enumerate(plan.series):
        series = item.series
        assert series.kind == (
            TransactionKindEnum.OPEN if index < 5 else TransactionKindEnum.CLOSED
        )
        assert series.credit_card_id is None
        assert series.subcategory_id is None
        if series.frequency_unit == TransactionFrequencyUnitEnum.WEEK:
            assert series.week_day == series.start_date.isoweekday()
            assert series.day_of_month is None
        else:
            assert series.week_day is None
            assert series.day_of_month == series.start_date.day
        assert series.month == (
            series.start_date.month
            if series.frequency_unit == TransactionFrequencyUnitEnum.YEAR
            else None
        )
        assert item.occurrences
        if series.kind == TransactionKindEnum.CLOSED:
            template = installments[series.name]
            assert (
                template.installments_range.min
                <= series.installments
                <= template.installments_range.max
            )
            assert len(item.occurrences) == series.installments
            assert item.occurrences[-1].expected_on == series.end_date
            assert series.direction == TransactionDirectionEnum.OUT
            total = sum(child.value for child in item.occurrences)
            assert template.total_range.min <= total <= template.total_range.max
            assert all(
                child.value - series.value in (Decimal(0), Decimal("0.01"))
                for child in item.occurrences
            )
        else:
            template = recurrences[series.name]
            assert series.frequency_unit == template.unit
            assert series.direction == template.direction
            assert template.value_range.min <= series.value <= template.value_range.max
            assert series.end_date is None
            assert series.installments is None
            assert all(child.expected_on <= plan.end_date for child in item.occurrences)
        for offset, child in enumerate(item.occurrences):
            assert child.occurrence_index == offset + 1
            expected = (
                series.start_date + timedelta(weeks=offset)
                if series.frequency_unit == TransactionFrequencyUnitEnum.WEEK
                else _shift_month(
                    series.start_date,
                    offset
                    * (
                        12
                        if series.frequency_unit == TransactionFrequencyUnitEnum.YEAR
                        else 1
                    ),
                )
            )
            assert child.occurrence_on == child.expected_on == expected
            for field in (
                "name",
                "direction",
                "account_id",
                "credit_card_id",
                "subcategory_id",
            ):
                assert getattr(child, field) == getattr(series, field)
            if series.kind == TransactionKindEnum.OPEN:
                assert child.value == series.value
            assert child.settled_on == (
                child.expected_on if child.expected_on < date(2026, 11, 4) else None
            )


@pytest.mark.parametrize("unit", ["WEEK", "MONTH", "YEAR"])
def test_recurrence_catalog_controls_frequency_direction_value_and_category(unit):
    template = RecurrenceSeedTemplate(
        name="Recurring income",
        direction="IN",
        unit=unit,
        valueRange={"min": "123.45", "max": "123.45"},
        weight=1,
        categoryHint="Income",
    )
    plan = build_plan(
        payload=TransactionSeedRequestSchema(
            transactions=0, recurrences=1, installment_plans=0, months=24
        ),
        today=date(2026, 12, 31),
        recurrence_templates=[template],
        subcategories={"Income": UUID(int=4)},
    )
    item = plan.series[0]
    series = item.series
    assert series.name == "Recurring income"
    assert series.direction == TransactionDirectionEnum.IN
    assert series.value == Decimal("123.45")
    assert series.credit_card_id is None
    assert series.subcategory_id == UUID(int=4)
    assert series.frequency_unit == unit
    for offset, child in enumerate(item.occurrences):
        expected = (
            series.start_date + timedelta(weeks=offset)
            if unit == "WEEK"
            else _shift_month(series.start_date, offset * (12 if unit == "YEAR" else 1))
        )
        assert child.expected_on == child.occurrence_on == expected
        assert child.value == series.value
        assert child.subcategory_id == series.subcategory_id
    assert item.occurrences[-1].expected_on <= plan.end_date
    next_offset = len(item.occurrences)
    next_date = (
        series.start_date + timedelta(weeks=next_offset)
        if unit == "WEEK"
        else _shift_month(
            series.start_date, next_offset * (12 if unit == "YEAR" else 1)
        )
    )
    assert next_date > plan.end_date


@pytest.mark.parametrize("quantity", [3, 18, 24])
def test_installment_catalog_total_is_split_without_losing_cents(quantity):
    template = InstallmentPlanSeedTemplate(
        name="Test purchase",
        totalRange={"min": 100, "max": 100},
        installmentsRange={"min": quantity, "max": quantity},
        weight=1,
        categoryHint="Purchase",
    )
    plan = build_plan(
        payload=TransactionSeedRequestSchema(
            transactions=0, recurrences=0, installment_plans=1, months=1
        ),
        installment_templates=[template],
        subcategories={"Purchase": UUID(int=5)},
    )
    item = plan.series[0]
    assert item.series.name == "Test purchase"
    assert item.series.direction == TransactionDirectionEnum.OUT
    assert item.series.subcategory_id == UUID(int=5)
    assert item.series.frequency_unit == TransactionFrequencyUnitEnum.MONTH
    assert item.series.installments == quantity
    assert len(item.occurrences) == quantity
    assert item.series.end_date == item.occurrences[-1].expected_on > plan.end_date
    assert sum(child.value for child in item.occurrences) == Decimal(100)
    assert max(child.value for child in item.occurrences) - min(
        child.value for child in item.occurrences
    ) <= Decimal("0.01")
    for child in item.occurrences:
        assert child.value > 0
        assert child.value == child.value.quantize(Decimal("0.01"))
        assert child.subcategory_id == item.series.subcategory_id


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            RecurrenceSeedTemplate,
            {
                "name": "Invalid",
                "direction": "OUT",
                "unit": "DAY",
                "valueRange": {"min": 1, "max": 2},
                "weight": 1,
            },
        ),
        (
            RecurrenceSeedTemplate,
            {
                "name": "Invalid",
                "direction": "OUT",
                "unit": "MONTH",
                "valueRange": {"min": 2, "max": 1},
                "weight": 1,
            },
        ),
        (
            InstallmentPlanSeedTemplate,
            {
                "name": "Invalid",
                "totalRange": {"min": 1, "max": 2},
                "installmentsRange": {"min": 6, "max": 2},
                "weight": 1,
            },
        ),
        (
            InstallmentPlanSeedTemplate,
            {
                "name": "Invalid",
                "totalRange": {"min": 1, "max": 2},
                "installmentsRange": {"min": 2, "max": 25},
                "weight": 1,
            },
        ),
        (
            InstallmentPlanSeedTemplate,
            {
                "name": "Invalid",
                "totalRange": {"min": "0.01", "max": 2},
                "installmentsRange": {"min": 2, "max": 3},
                "weight": 1,
            },
        ),
    ],
)
def test_series_catalog_validation_rejects_invalid_templates(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize(
    "loader", [load_seeds_recurrences, load_seeds_installment_plans]
)
def test_series_catalogs_reject_empty_files(loader, monkeypatch):
    monkeypatch.setattr(
        "app.domain.transaction.seeds.Path.read_text", lambda *args, **kwargs: "[]"
    )
    with pytest.raises(ValueError, match="must not be empty"):
        loader()


def test_calendar_handles_leap_year_and_month_end_without_drift():
    first = date(2024, 1, 31)
    assert _shift_month(first, 1) == date(2024, 2, 29)
    assert _shift_month(first, 2) == date(2024, 3, 31)
    plan = build_plan(
        payload=TransactionSeedRequestSchema(months=3),
        today=date(2025, 1, 1),
    )
    assert plan.start_date == date(2024, 11, 1)
    assert plan.end_date == date(2025, 1, 31)


@pytest_asyncio.fixture
async def seed_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: table_registry.metadata.create_all(
                sync,
                tables=[
                    Account.__table__,
                    CreditCard.__table__,
                    Transaction.__table__,
                    TransactionSeries.__table__,
                    ScheduledTransaction.__table__,
                ],
            )
        )
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


@pytest.fixture
def seed_service(seed_session, monkeypatch):
    service = TransactionService.from_session(seed_session)
    # Category DDL uses PostgreSQL-only constraints; its owner query is tested separately.
    monkeypatch.setattr(
        service.repository, "seed_subcategories", AsyncMock(return_value={})
    )
    for service_class in (
        TransactionService,
        TransactionSeriesService,
        ScheduledTransactionService,
    ):
        monkeypatch.setattr(service_class, "_invalidate_cache", AsyncMock())
    return service


def make_account(user_id, **overrides):
    return Account(
        **(
            {
                "user_id": user_id,
                "name": "Seed account",
                "description": None,
                "type": AccountTypeEnum.CHECKING,
                "account_number": None,
                "agency": None,
                "financial_institution": None,
                "color": None,
                "icon": None,
            }
            | overrides
        )
    )


@pytest.mark.asyncio
@freeze_time("2026-11-04")
async def test_seed_persists_whole_aggregate_with_owner_isolation(
    seed_service, seed_session, admin
):
    own = make_account(admin.id)
    foreign = make_account(uuid4())
    inactive = make_account(admin.id, is_active=False)
    deleted = make_account(admin.id)
    deleted.deleted_at = date(2026, 1, 1)
    card = CreditCard(
        user_id=admin.id,
        name="Card",
        description=None,
        brand=CreditCardBrandEnum.VISA,
        last_four_digits=None,
        closing_day=10,
        due_day=15,
        limit=None,
        color=None,
        icon=None,
    )
    seed_session.add_all([own, foreign, inactive, deleted, card])
    await seed_session.commit()
    payload = TransactionSeedRequestSchema(
        transactions=20, recurrences=2, installment_plans=2, seed=0
    )
    result = await seed_service.seed(user=admin, payload=payload)
    assert result.seed == 0
    assert result.transactions == 20
    assert result.transaction_series == 4
    assert result.scheduled_transactions >= 6
    for model, count in (
        (Transaction, result.transactions),
        (TransactionSeries, result.transaction_series),
        (ScheduledTransaction, result.scheduled_transactions),
    ):
        rows = list(await seed_session.scalars(select(model)))
        assert len(rows) == count
        assert all(row.user_id == admin.id and row.account_id == own.id for row in rows)
        assert all(row.credit_card_id in (None, card.id) for row in rows)
    children = list(await seed_session.scalars(select(ScheduledTransaction)))
    parents = {
        row.id: row for row in await seed_session.scalars(select(TransactionSeries))
    }
    assert all(child.transaction_series_id in parents for child in children)
    recurrence_names = {template.name for template in load_seeds_recurrences()}
    installment_names = {template.name for template in load_seeds_installment_plans()}
    for parent in parents.values():
        assert parent.name in (
            recurrence_names
            if parent.kind == TransactionKindEnum.OPEN
            else installment_names
        )
    assert all(
        child.name == parents[child.transaction_series_id].name for child in children
    )
    await seed_service.seed(user=admin, payload=payload)
    assert (
        await seed_session.scalar(select(func.count()).select_from(Transaction)) == 40
    )
    assert (
        await seed_session.scalar(select(func.count()).select_from(TransactionSeries))
        == 8
    )
    seed_service._invalidate_cache.assert_awaited()


@pytest.mark.asyncio
async def test_seed_rolls_back_after_database_flush(
    seed_service, seed_session, admin, monkeypatch
):
    seed_session.add(make_account(admin.id))
    await seed_session.commit()
    original = seed_service.repository.save_seed

    async def fail_after_flush(**kwargs):
        await original(**kwargs)
        raise SQLAlchemyError("Seed persistence failed")

    monkeypatch.setattr(seed_service.repository, "save_seed", fail_after_flush)
    with pytest.raises(HTTPException) as error:
        await seed_service.seed(
            user=admin, payload=TransactionSeedRequestSchema(seed=42)
        )
    assert error.value.status_code == 500
    for model in (Transaction, TransactionSeries, ScheduledTransaction):
        assert await seed_session.scalar(select(func.count()).select_from(model)) == 0
    seed_service._invalidate_cache.assert_not_awaited()


@pytest.mark.asyncio
async def test_seed_requires_own_active_account(seed_service, seed_session, admin):
    seed_session.add_all(
        [make_account(uuid4()), make_account(admin.id, is_active=False)]
    )
    await seed_session.commit()
    with pytest.raises(HTTPException) as error:
        await seed_service.seed(user=admin, payload=TransactionSeedRequestSchema())
    assert error.value.status_code == 409
    assert await seed_session.scalar(select(func.count()).select_from(Transaction)) == 0


@pytest.mark.asyncio
async def test_seed_subcategory_lookup_filters_owner_and_visibility(
    transaction_session, user
):
    transaction_session.execute.return_value = [
        ("Supermercado", UUID(int=2)),
        ("Supermercado", UUID(int=3)),
    ]
    result = await TransactionRepository(transaction_session).seed_subcategories(
        user_id=user.id
    )
    query = transaction_session.execute.await_args.args[0]
    sql = str(query)
    assert "categories.user_id =" in sql
    assert user.id in query.compile().params.values()
    for table in ("categories", "subcategories"):
        assert f"{table}.deleted_at IS NULL" in sql
        assert f"{table}.is_active IS true" in sql
    assert result == {"Supermercado": UUID(int=2)}
