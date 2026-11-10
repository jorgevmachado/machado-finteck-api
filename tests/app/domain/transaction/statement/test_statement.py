from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Column, MetaData, String, Table, event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.database import get_session
from app.core.database.base import table_registry
from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.transaction.route import router
from app.domain.transaction.schema import TransactionCreateSchema
from app.domain.transaction.series.schema import TransactionSeriesCreateSchema
from app.domain.transaction.statement.business import combine_statement, project_series
from app.domain.transaction.statement.repository import StatementRepository
from app.domain.transaction.statement.route import statement_service
from app.domain.transaction.statement.schema import (
    StatementEntrySchema,
    StatementFilterSchema,
    StatementSeriesSchema,
)
from app.domain.transaction.statement.service import StatementService
from app.models import (
    Account,
    Category,
    CreditCard,
    ScheduledTransaction,
    Subcategory,
    Transaction,
    TransactionSeries,
    utcnow,
)
from app.shared.schemas import FilterPage


def period(start="2026-11-01", end="2026-11-30", **kwargs):
    return StatementFilterSchema(
        start_date=start, end_date=end, **{"page": 1, **kwargs}
    )


def make_account(user_id, account_id):
    account = Account(
        user_id=user_id,
        name="Main account",
        description=None,
        type="CHECKING",
        account_number=None,
        agency=None,
        financial_institution=None,
        color=None,
        icon=None,
    )
    account.id = account_id
    return account


def make_card(user_id, card_id):
    card = CreditCard(
        user_id=user_id,
        name="Main card",
        description=None,
        brand="VISA",
        last_four_digits=None,
        closing_day=5,
        due_day=15,
        limit=Decimal("1000.00"),
        color=None,
        icon=None,
    )
    card.id = card_id
    return card


def make_subcategory(
    subcategory_id, user_id=None, name="Groceries", category_name="Essentials"
):
    category = Category(user_id=user_id or uuid4(), name=category_name)
    subcategory = Subcategory(name=name, order=1)
    subcategory.id = subcategory_id
    subcategory.category_id = category.id
    subcategory.category = category
    return subcategory


def make_series(user_id, **kwargs):
    payload = TransactionSeriesCreateSchema.model_validate(
        {
            "kind": "OPEN",
            "name": "Subscription",
            "value": "100.00",
            "direction": "OUT",
            "account_id": uuid4(),
            "start_date": "2026-01-10",
            "frequency_unit": "MONTH",
            "frequency_interval": 1,
            "day_of_month": 10,
            **kwargs,
        }
    )
    entity = TransactionSeries(user_id=user_id, **payload.model_dump())
    entity.account = make_account(user_id, entity.account_id)
    entity.credit_card = (
        make_card(user_id, entity.credit_card_id) if entity.credit_card_id else None
    )
    entity.subcategory = (
        make_subcategory(entity.subcategory_id, user_id=user_id)
        if entity.subcategory_id
        else None
    )
    return entity


def projected(entity, filters):
    return project_series(StatementSeriesSchema.model_validate(entity), filters)


@pytest.mark.parametrize(
    ("kwargs", "start", "end", "expected", "indices"),
    [
        ({}, "2026-11-01", "2026-12-31", ["2026-11-10", "2026-12-10"], [11, 12]),
        ({"frequency_interval": 2}, "2026-11-11", "2027-01-31", ["2027-01-10"], [7]),
        (
            {"start_date": "2026-09-15"},
            "2026-09-01",
            "2026-11-30",
            ["2026-10-10", "2026-11-10"],
            [1, 2],
        ),
        (
            {
                "frequency_unit": "WEEK",
                "start_date": "2026-11-04",
                "week_day": 1,
                "day_of_month": None,
            },
            "2026-11-01",
            "2026-11-30",
            ["2026-11-09", "2026-11-16", "2026-11-23", "2026-11-30"],
            [1, 2, 3, 4],
        ),
        (
            {
                "frequency_unit": "WEEK",
                "start_date": "2026-10-26",
                "week_day": 1,
                "day_of_month": None,
                "frequency_interval": 2,
            },
            "2026-11-10",
            "2026-11-30",
            ["2026-11-23"],
            [3],
        ),
        (
            {"start_date": "2024-01-31", "day_of_month": 31},
            "2024-01-01",
            "2024-03-31",
            ["2024-01-31", "2024-02-29", "2024-03-31"],
            [1, 2, 3],
        ),
        (
            {"start_date": "2025-01-31", "day_of_month": 31},
            "2025-01-01",
            "2025-03-31",
            ["2025-01-31", "2025-02-28", "2025-03-31"],
            [1, 2, 3],
        ),
        (
            {
                "frequency_unit": "YEAR",
                "start_date": "2024-02-29",
                "month": 2,
                "day_of_month": 29,
            },
            "2025-01-01",
            "2025-12-31",
            ["2025-02-28"],
            [2],
        ),
        (
            {
                "frequency_unit": "YEAR",
                "start_date": "2024-02-29",
                "month": 2,
                "day_of_month": 29,
            },
            "2028-01-01",
            "2028-12-31",
            ["2028-02-29"],
            [5],
        ),
        (
            {
                "frequency_unit": "YEAR",
                "start_date": "2026-09-15",
                "month": 6,
                "day_of_month": 10,
            },
            "2027-01-01",
            "2027-12-31",
            ["2027-06-10"],
            [1],
        ),
        (
            {"kind": "CLOSED", "installments": 2},
            "2026-01-10",
            "2026-03-31",
            ["2026-01-10", "2026-02-10"],
            [1, 2],
        ),
        (
            {"end_date": "2026-02-10"},
            "2026-01-10",
            "2026-03-31",
            ["2026-01-10", "2026-02-10"],
            [1, 2],
        ),
        ({"kind": "CLOSED", "installments": 2}, "2026-11-01", "2026-11-30", [], []),
        ({"start_date": "2027-01-10"}, "2026-11-01", "2026-11-30", [], []),
        ({"day_of_month": None}, "2026-11-10", "2026-11-10", ["2026-11-10"], [11]),
        (
            {"start_date": "9999-12-10"},
            "9999-12-01",
            "9999-12-31",
            ["9999-12-10"],
            [1],
        ),
        (
            {"frequency_unit": "WEEK", "start_date": "9999-12-31", "week_day": 1},
            "9999-12-01",
            "9999-12-31",
            [],
            [],
        ),
        (
            {
                "frequency_unit": "YEAR",
                "start_date": "9999-12-31",
                "month": 1,
                "day_of_month": 10,
            },
            "9999-12-01",
            "9999-12-31",
            [],
            [],
        ),
    ],
)
def test_projection_obeys_calendar_anchors_intervals_and_limits(
    user, kwargs, start, end, expected, indices
):
    entity = make_series(user.id, **kwargs)
    entries = projected(entity, period(start, end))
    assert [entry.expected_on.isoformat() for entry in entries] == expected
    assert [entry.occurrence_index for entry in entries] == indices
    assert projected(entity, period(start, end)) == entries
    for entry in entries:
        assert entry.id is None
        assert entry.source == "PROJECTED"
        assert entry.status == "PENDING"
        assert entry.settled_on is None
        assert entry.occurrence_on == entry.expected_on
        assert entry.value == Decimal("100.00")
        assert entry.transaction_serie is not None
        assert entry.transaction_serie.id == entity.id
        assert entry.transaction_serie.name == entity.name


def test_projection_copies_subcategory_and_category_names(user):
    subcategory_id = uuid4()
    entity = make_series(user.id, subcategory_id=subcategory_id)
    entries = projected(entity, period())

    assert entries
    for entry in entries:
        assert entry.subcategory is not None
        assert entry.subcategory_name == "Groceries"
        assert entry.category_id == entity.subcategory.category_id
        assert entry.category_name == "Essentials"


def test_projection_leaves_category_fields_null_without_subcategory(user):
    entity = make_series(user.id)
    entries = projected(entity, period())

    assert entries
    for entry in entries:
        assert entry.subcategory is None
        assert entry.subcategory_name is None
        assert entry.category_id is None
        assert entry.category_name is None


@pytest.mark.parametrize(
    "values",
    [
        {"frequency_interval": 0},
        {"kind": "CLOSED", "installments": None},
        {"week_day": 0},
        {"day_of_month": 32},
        {"month": 13},
        {"end_date": "2025-01-01"},
    ],
)
def test_invalid_stored_series_fail_explicitly(user, values):
    with pytest.raises(ValidationError):
        StatementSeriesSchema.model_validate(make_series(user.id, **values))


@pytest_asyncio.fixture
async def statement_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: table_registry.metadata.create_all(
                sync,
                tables=[
                    Transaction.__table__,
                    TransactionSeries.__table__,
                    ScheduledTransaction.__table__,
                    Account.__table__,
                    CreditCard.__table__,
                ],
            )
        )
        # PostgreSQL-specific category constraints are covered by integration tests.
        metadata = MetaData()
        Table(
            "categories",
            metadata,
            *(
                Column(
                    column.name,
                    String() if column.name == "name" else column.type,
                    primary_key=column.primary_key,
                )
                for column in Category.__table__.columns
            ),
        )
        Table(
            "subcategories",
            metadata,
            *(
                Column(
                    column.name,
                    String() if column.name == "name" else column.type,
                    primary_key=column.primary_key,
                )
                for column in Subcategory.__table__.columns
            ),
        )
        await connection.run_sync(metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


def make_transaction(user_id, account_id, **kwargs):
    payload = TransactionCreateSchema.model_validate(
        {
            "name": "Market",
            "value": "50.00",
            "direction": "OUT",
            "expected_on": "2026-11-15",
            "account_id": account_id,
            **kwargs,
        }
    )
    return Transaction(user_id=user_id, **payload.model_dump())


def make_scheduled(entity, **kwargs):
    scheduled = ScheduledTransaction(
        **{
            "user_id": entity.user_id,
            "account_id": entity.account_id,
            "transaction_series_id": entity.id,
            "subcategory_id": entity.subcategory_id,
            "credit_card_id": entity.credit_card_id,
            "name": entity.name,
            "direction": entity.direction,
            "status": "PENDING",
            "expected_on": date(2026, 11, 10),
            "settled_on": None,
            "note": None,
            "occurrence_on": date(2026, 11, 10),
            "occurrence_index": 11,
            "value": Decimal("100.00"),
            **kwargs,
        }
    )
    scheduled.account = (
        entity.account
        if scheduled.account_id == entity.account_id
        else make_account(scheduled.user_id, scheduled.account_id)
    )
    scheduled.credit_card = (
        entity.credit_card
        if scheduled.credit_card_id == entity.credit_card_id
        else make_card(scheduled.user_id, scheduled.credit_card_id)
        if scheduled.credit_card_id
        else None
    )
    scheduled.subcategory = (
        entity.subcategory
        if scheduled.subcategory_id == entity.subcategory_id
        else make_subcategory(scheduled.subcategory_id, user_id=scheduled.user_id)
        if scheduled.subcategory_id
        else None
    )
    return scheduled


@pytest.mark.asyncio
async def test_statement_merges_overrides_and_moved_dates_without_writing(
    statement_session, user
):
    entity = make_series(user.id)
    entity_id = entity.id
    transaction = make_transaction(user.id, entity.account_id)
    moved = make_scheduled(
        entity, expected_on=date(2026, 12, 5), value=Decimal("125.00")
    )
    statement_session.add_all([entity, transaction, moved])
    await statement_session.commit()
    statement_session.expunge_all()
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(statement_session.bind.sync_engine, "before_cursor_execute", capture)
    try:
        service = StatementService.from_session(statement_session)
        november = await service.list_all(user=user, page_filter=period())
        assert november.meta.total == 1
        assert november.items[0].source == "TRANSACTION"
        assert november.items[0].transaction_serie is None
        december = await service.list_all(
            user=user, page_filter=period("2026-12-01", "2026-12-31")
        )
        assert [(entry.source, entry.occurrence_index) for entry in december.items] == [
            ("PROJECTED", 12),
            ("SCHEDULED", 11),
        ]
        recorded = december.items[1]
        assert recorded.occurrence_on == date(2026, 11, 10)
        assert recorded.expected_on == date(2026, 12, 5)
        assert recorded.value == Decimal("125.00")
        assert recorded.series_name == "Subscription"
        assert recorded.transaction_serie is not None
        assert recorded.transaction_serie.id == entity_id
        assert recorded.transaction_serie.kind == entity.kind
        assert recorded.transaction_serie.account.id == entity.account_id
        assert all(
            statement.lstrip().upper().startswith("SELECT") for statement in statements
        )
        assert not statement_session.new
        assert not statement_session.dirty
    finally:
        event.remove(
            statement_session.bind.sync_engine, "before_cursor_execute", capture
        )


@pytest.mark.asyncio
async def test_statement_paginates_combined_filtered_entries(statement_session, user):
    entity = make_series(user.id)
    moved = make_scheduled(entity, expected_on=date(2026, 12, 5))
    transactions = [
        make_transaction(
            user.id, entity.account_id, name=name, expected_on=date(2026, 11, day)
        )
        for name, day in (("Alpha", 20), ("Beta", 19), ("Gamma", 18))
    ]
    excluded = make_transaction(
        user.id, entity.account_id, status="SETTLED", settled_on=date(2026, 11, 10)
    )
    statement_session.add_all([entity, moved, excluded, *transactions])
    await statement_session.commit()
    service = StatementService.from_session(statement_session)
    filters = period(end="2026-12-31", limit=2, status="PENDING")
    assert isinstance(filters, FilterPage)
    first = await service.list_all(user=user, page_filter=filters)
    assert isinstance(first, CustomLimitOffsetPage)
    assert [entry.source for entry in first.items] == ["PROJECTED", "SCHEDULED"]
    assert first.meta.model_dump() == {
        "total": 5,
        "limit": 2,
        "offset": 0,
        "next_page": 2,
        "previous_page": None,
        "total_pages": 3,
        "current_page": 1,
    }
    second = await service.list_all(user=user, page_filter=filters.with_updates(page=2))
    assert [entry.name for entry in second.items] == ["Alpha", "Beta"]
    assert second.meta.total == 5
    assert second.meta.previous_page == 1
    assert second.meta.next_page == 3
    last = await service.list_all(user=user, page_filter=filters.with_updates(page=3))
    assert [entry.name for entry in last.items] == ["Gamma"]
    assert last.meta.next_page is None
    by_offset = await service.list_all(
        user=user, page_filter=filters.model_copy(update={"page": None, "offset": 2})
    )
    assert by_offset == second
    beyond = await service.list_all(user=user, page_filter=filters.with_updates(page=4))
    assert beyond.items == []
    assert beyond.meta.total == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("order_by", "order", "expected"),
    [
        ("name", "asc", ["Alpha", "Beta", "Subscription"]),
        ("name", "desc", ["Subscription", "Beta", "Alpha"]),
        ("value", "asc", ["Beta", "Alpha", "Subscription"]),
        ("value", "desc", ["Subscription", "Alpha", "Beta"]),
        ("expected_on", "asc", ["Subscription", "Beta", "Alpha"]),
    ],
)
async def test_statement_orders_before_paginating(
    statement_session, user, order_by, order, expected
):
    entity = make_series(user.id)
    statement_session.add_all(
        [
            entity,
            make_transaction(
                user.id,
                entity.account_id,
                name="Alpha",
                value="20.00",
                expected_on=date(2026, 11, 20),
            ),
            make_transaction(
                user.id,
                entity.account_id,
                name="Beta",
                value="10.00",
                expected_on=date(2026, 11, 19),
            ),
        ]
    )
    await statement_session.commit()
    service = StatementService.from_session(statement_session)
    filters = period(order_by=order_by, order=order, limit=1)
    for page, name in enumerate(expected, start=1):
        result = await service.list_all(
            user=user, page_filter=filters.with_updates(page=page)
        )
        assert [entry.name for entry in result.items] == [name]
        assert result.meta.total == 3
    unpaginated = await service.list_all(
        user=user, page_filter=filters.model_copy(update={"page": None})
    )
    assert isinstance(unpaginated, list)
    assert [entry.name for entry in unpaginated] == expected


@pytest.mark.asyncio
async def test_statement_uses_shared_limit_cap(statement_session, user):
    statement_session.add(
        make_series(user.id, frequency_unit="WEEK", start_date="2026-01-01", week_day=4)
    )
    await statement_session.commit()
    result = await StatementService.from_session(statement_session).list_all(
        user=user,
        page_filter=period("2026-01-01", "2026-12-31", limit=200),
    )
    assert result.meta.limit == 100
    assert result.meta.total == 53


@pytest.mark.asyncio
async def test_stored_values_win_and_filters_apply_after_override(
    statement_session, user
):
    entity = make_series(user.id)
    card_id = uuid4()
    subcategory_id = uuid4()
    account_id = uuid4()
    occurrence = make_scheduled(
        entity,
        name="CHANGED income",
        value=Decimal("175.00"),
        status="SETTLED",
        settled_on=date(2026, 11, 10),
        direction="IN",
        credit_card_id=card_id,
        subcategory_id=subcategory_id,
        account_id=account_id,
    )
    statement_session.add_all([entity, occurrence])
    await statement_session.commit()
    service = StatementService.from_session(statement_session)
    for filters in (
        period(status="SETTLED"),
        period(search="changed"),
        period(direction="IN"),
        period(account_id=account_id),
        period(subcategory_id=subcategory_id),
        period(only_credit_card=True),
        period(credit_card_id=card_id, only_credit_card=False),
    ):
        result = await service.list_all(user=user, page_filter=filters)
        assert result.meta.total == 1
        assert result.items[0].source == "SCHEDULED"
        assert result.items[0].value == Decimal("175.00")
    for filters in (
        period(status="PENDING"),
        period(direction="OUT"),
        period(search="Subscription"),
        period(account_id=entity.account_id),
        period(only_credit_card=False),
        period(credit_card_id=uuid4()),
        period(subcategory_id=uuid4()),
    ):
        assert (await service.list_all(user=user, page_filter=filters)).meta.total == 0


@pytest.mark.asyncio
async def test_canceled_occurrence_remains_visible_without_pending_duplicate(
    statement_session, user
):
    entity = make_series(user.id)
    canceled = make_scheduled(entity, status="CANCELED")
    statement_session.add_all([entity, canceled])
    await statement_session.commit()
    service = StatementService.from_session(statement_session)
    result = await service.list_all(user=user, page_filter=period())
    assert result.meta.total == 1
    assert result.items[0].source == "SCHEDULED"
    assert result.items[0].status == "CANCELED"
    assert (
        await service.list_all(user=user, page_filter=period(status="PENDING"))
    ).meta.total == 0
    await statement_session.delete(canceled)
    await statement_session.commit()
    reverted = await service.list_all(user=user, page_filter=period())
    assert reverted.meta.total == 1
    assert reverted.items[0].source == "PROJECTED"


@pytest.mark.asyncio
async def test_owner_isolation_deleted_roots_and_moved_closed_occurrence(
    statement_session, user
):
    closed = make_series(user.id, kind="CLOSED", installments=1, end_date="2026-01-10")
    moved = make_scheduled(
        closed,
        occurrence_index=1,
        occurrence_on=date(2026, 1, 10),
    )
    foreign = make_series(uuid4())
    foreign_entry = make_scheduled(foreign)
    forged_owner = make_scheduled(foreign, user_id=user.id)
    deleted = make_series(user.id)
    deleted.deleted_at = utcnow()
    deleted_child = make_scheduled(deleted)
    hidden_transaction = make_transaction(user.id, closed.account_id)
    hidden_transaction.deleted_at = utcnow()
    statement_session.add_all(
        [
            closed,
            moved,
            foreign,
            foreign_entry,
            forged_owner,
            deleted,
            deleted_child,
            hidden_transaction,
            make_transaction(foreign.user_id, foreign.account_id),
        ]
    )
    await statement_session.commit()
    result = await StatementService.from_session(statement_session).list_all(
        user=user, page_filter=period()
    )
    assert result.meta.total == 1
    assert result.items[0].id == moved.id
    assert result.items[0].installments == 1


def test_duplicate_overrides_are_reported_instead_of_silently_discarded(user):
    entity = make_series(user.id)
    entry = projected(entity, period())[0].model_copy(update={"source": "SCHEDULED"})
    with pytest.raises(ValueError, match="Duplicate scheduled"):
        combine_statement(
            transactions=[], projections=[], scheduled=[entry, entry], filters=period()
        )


def test_order_is_deterministic_for_same_date_and_multiple_sources(user):
    entity = make_series(user.id)
    projection = projected(entity, period())[0]
    scheduled = projection.model_copy(
        update={
            "source": "SCHEDULED",
            "id": uuid4(),
            "transaction_serie": projection.transaction_serie.model_copy(
                update={"id": uuid4()}
            ),
        }
    )
    transaction = projection.model_copy(
        update={
            "source": "TRANSACTION",
            "id": uuid4(),
            "transaction_serie": None,
        }
    )
    result = combine_statement(
        transactions=[transaction],
        projections=[projection],
        scheduled=[scheduled],
        filters=period(),
    )
    assert [entry.source for entry in result] == [
        "TRANSACTION",
        "SCHEDULED",
        "PROJECTED",
    ]


@pytest.fixture
def statement_client(user):
    app = FastAPI()
    app.include_router(router, prefix="/transactions")
    service = AsyncMock()
    service.list_all.return_value = []
    app.dependency_overrides[statement_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        yield client, service


def test_statement_http_validates_and_delegates(statement_client, user):
    client, service = statement_client
    response = client.get(
        "/transactions/statement",
        params={
            "start_date": "2026-11-01",
            "end_date": "2026-11-30",
            "status": "PENDING",
        },
    )
    assert response.status_code == 200
    assert response.json() == []
    service.list_all.assert_awaited_once_with(
        user=user, page_filter=period(status="PENDING", page=None)
    )


@pytest.mark.parametrize("field", ["account_id", "credit_card_id", "subcategory_id"])
def test_statement_http_accepts_uuid_filters(statement_client, user, field):
    client, service = statement_client
    identifier = uuid4()
    response = client.get(
        "/transactions/statement",
        params={
            "start_date": "2026-11-01",
            "end_date": "2026-11-30",
            field: str(identifier),
        },
    )
    assert response.status_code == 200
    assert response.json() == []
    service.list_all.assert_awaited_once_with(
        user=user, page_filter=period(page=None, **{field: identifier})
    )


@pytest.mark.parametrize("field", ["account_id", "credit_card_id", "subcategory_id"])
def test_statement_http_rejects_invalid_uuid_filters(statement_client, field):
    client, service = statement_client
    response = client.get(
        "/transactions/statement",
        params={
            "start_date": "2026-11-01",
            "end_date": "2026-11-30",
            field: "INVALID",
        },
    )
    assert response.status_code == 422
    service.list_all.assert_not_awaited()


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"start_date": "2026-11-01"},
        {"start_date": "2026-11-30", "end_date": "2026-11-01"},
        {"start_date": "2026-02-01", "end_date": "2026-02-30"},
        {"start_date": "2026-01-01", "end_date": "2027-01-02"},
        {"start_date": "2026-11-01", "end_date": "2026-11-30", "status": "INVALID"},
        {"start_date": "2026-11-01", "end_date": "2026-11-30", "account_id": "INVALID"},
        {"start_date": "2026-11-01", "end_date": "2026-11-30", "unexpected": True},
        {"start_date": "2026-11-01", "end_date": "2026-11-30", "page": -1},
        {"start_date": "2026-11-01", "end_date": "2026-11-30", "offset": -1},
        {"start_date": "2026-11-01", "end_date": "2026-11-30", "limit": 0},
        {"start_date": "2026-11-01", "end_date": "2026-11-30", "order_by": "invalid"},
        {"start_date": "2026-11-01", "end_date": "2026-11-30", "order": "invalid"},
    ],
)
def test_statement_http_rejects_invalid_filters(statement_client, params):
    client, service = statement_client
    assert client.get("/transactions/statement", params=params).status_code == 422
    service.list_all.assert_not_awaited()


def test_statement_http_requires_authentication():
    app = FastAPI()
    app.include_router(router, prefix="/transactions")
    service = AsyncMock()
    app.dependency_overrides[statement_service] = lambda: service
    with TestClient(app) as client:
        response = client.get(
            "/transactions/statement",
            params={
                "start_date": "2026-11-01",
                "end_date": "2026-11-30",
            },
        )
    assert response.status_code == 401
    service.list_all.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("pagination", [{}, {"page": 1}, {"offset": 0, "limit": 1}])
async def test_http_real_statement_service_returns_projected_entries_without_insert(
    statement_session, user, pagination
):
    entity = make_series(user.id)
    statement_session.add(entity)
    await statement_session.commit()
    app = FastAPI()
    app.include_router(router, prefix="/transactions")
    app.dependency_overrides[get_session] = lambda: statement_session
    app.dependency_overrides[get_current_user] = lambda: user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/transactions/statement",
            params={
                "start_date": "2026-11-01",
                "end_date": "2026-11-30",
                **pagination,
            },
        )
    assert response.status_code == 200
    payload = response.json()
    if pagination:
        assert payload["meta"]["total"] == 1
        assert payload["meta"]["limit"] == pagination.get("limit", 12)
        entry = payload["items"][0]
    else:
        assert isinstance(payload, list)
        entry = payload[0]
    assert entry["source"] == "PROJECTED"
    assert entry["id"] is None
    assert entry["value"] == "100.00"
    assert entry["account"]["id"] == str(entity.account_id)
    assert entry["credit_card"] is None
    assert entry["subcategory"] is None
    assert not {"account_id", "credit_card_id", "subcategory_id"} & entry.keys()
    assert entry["occurrence_index"] == 11
    assert "transaction_series_id" not in entry
    assert entry["transaction_serie"]["id"] == str(entity.id)
    assert entry["transaction_serie"]["name"] == "Subscription"
    assert entry["transaction_serie"]["kind"] == "OPEN"
    assert entry["transaction_serie"]["frequency_unit"] == "MONTH"
    assert entry["transaction_serie"]["account"]["id"] == str(entity.account_id)
    assert list(await statement_session.scalars(select(ScheduledTransaction))) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["TRANSACTION", "SCHEDULED", "PROJECTED"])
@pytest.mark.parametrize("with_optional_relations", [False, True])
async def test_statement_returns_nested_relations_for_each_source(
    statement_session, user, source, with_optional_relations
):
    relations = (
        {"credit_card_id": uuid4(), "subcategory_id": uuid4()}
        if with_optional_relations
        else {}
    )
    entity = make_series(
        user.id,
        start_date="2027-01-10" if source == "TRANSACTION" else "2026-01-10",
        **relations,
    )
    statement_session.add(entity)
    if source == "TRANSACTION":
        statement_session.add(make_transaction(user.id, entity.account_id, **relations))
    elif source == "SCHEDULED":
        statement_session.add(make_scheduled(entity))
    await statement_session.commit()
    account_id = entity.account_id
    category_id = entity.subcategory.category_id if entity.subcategory else None
    statement_session.expunge_all()

    app = FastAPI()
    app.include_router(router, prefix="/transactions")
    app.dependency_overrides[get_session] = lambda: statement_session
    app.dependency_overrides[get_current_user] = lambda: user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/transactions/statement",
            params={
                "start_date": "2026-11-01",
                "end_date": "2026-11-30",
                "account_id": str(account_id),
                **{field: str(value) for field, value in relations.items()},
            },
        )
    assert response.status_code == 200
    assert len(response.json()) == 1
    entry = response.json()[0]
    assert entry["source"] == source
    assert entry["account"]["id"] == str(account_id)
    assert entry["account"]["name"] == "Main account"
    assert entry["account"]["type"] == "CHECKING"
    assert not {"account_id", "credit_card_id", "subcategory_id"} & entry.keys()
    if source == "TRANSACTION":
        assert entry["transaction_serie"] is None
    else:
        assert entry["transaction_serie"]["id"] == str(entity.id)
        assert entry["transaction_serie"]["name"] == "Subscription"
        assert entry["transaction_serie"]["account"]["id"] == str(account_id)
    if with_optional_relations:
        assert entry["credit_card"]["id"] == str(relations["credit_card_id"])
        assert entry["credit_card"]["brand"] == "VISA"
        assert entry["subcategory"]["id"] == str(relations["subcategory_id"])
        assert entry["subcategory"]["name"] == "Groceries"
        assert entry["subcategory_name"] == "Groceries"
        assert entry["category_id"] == str(category_id)
        assert entry["category_name"] == "Essentials"
    else:
        assert entry["credit_card"] is None
        assert entry["subcategory"] is None
        assert entry["subcategory_name"] is None
        assert entry["category_id"] is None
        assert entry["category_name"] is None


@pytest.mark.asyncio
async def test_repository_loads_relations_before_synchronous_serialization(
    statement_session, user
):
    entity = make_series(user.id, credit_card_id=uuid4(), subcategory_id=uuid4())
    transaction = make_transaction(
        user.id,
        entity.account_id,
        credit_card_id=entity.credit_card_id,
        subcategory_id=entity.subcategory_id,
    )
    scheduled = make_scheduled(entity)
    statement_session.add_all([entity, transaction, scheduled])
    await statement_session.commit()
    series_id = entity.id
    statement_session.expunge_all()
    repository = StatementRepository(statement_session)
    filters = period()
    series = await repository.series(user_id=user.id, filters=filters)
    transactions = await repository.transactions(user_id=user.id, filters=filters)
    overrides = await repository.scheduled(
        user_id=user.id, filters=filters, projected_ranges={series_id: (11, 11)}
    )
    statement_session.expunge_all()

    series_dto = StatementSeriesSchema.model_validate(series[0])
    assert series_dto.account.name == "Main account"
    assert series_dto.credit_card.name == "Main card"
    assert series_dto.subcategory.name == "Groceries"
    for entry in [*transactions, *(override for override, _ in overrides)]:
        dto = StatementEntrySchema.model_validate(entry)
        assert dto.account == series_dto.account
        assert dto.credit_card == series_dto.credit_card
        assert dto.subcategory == series_dto.subcategory
    scheduled_dto = StatementEntrySchema.model_validate(overrides[0][0])
    assert scheduled_dto.transaction_serie is not None
    assert scheduled_dto.transaction_serie.id == series_id
    assert scheduled_dto.transaction_serie.account.name == "Main account"
    assert scheduled_dto.transaction_serie.credit_card.name == "Main card"
    assert scheduled_dto.transaction_serie.subcategory.name == "Groceries"


@pytest.mark.asyncio
async def test_scheduled_occurrence_keeps_own_relations_apart_from_series_relations(
    statement_session, user
):
    entity = make_series(user.id, credit_card_id=uuid4(), subcategory_id=uuid4())
    moved_account_id = uuid4()
    moved = make_scheduled(entity, account_id=moved_account_id)
    statement_session.add_all([entity, moved])
    await statement_session.commit()
    series_id = entity.id
    statement_session.expunge_all()

    scheduled = await StatementRepository(statement_session).scheduled(
        user_id=user.id, filters=period(), projected_ranges={series_id: (11, 11)}
    )
    statement_session.expunge_all()
    dto = StatementEntrySchema.model_validate(scheduled[0][0])

    assert dto.account.id == moved_account_id
    assert dto.transaction_serie is not None
    assert dto.transaction_serie.id == series_id
    assert dto.transaction_serie.account.id == entity.account_id
    assert dto.transaction_serie.account.id != dto.account.id


@pytest.mark.asyncio
async def test_scheduled_flat_category_fields_come_from_occurrence_not_series(
    statement_session, user
):
    entity = make_series(user.id, subcategory_id=uuid4())
    moved_subcategory_id = uuid4()
    moved = make_scheduled(entity, subcategory_id=moved_subcategory_id)
    statement_session.add_all([entity, moved])
    await statement_session.commit()
    series_id = entity.id
    statement_session.expunge_all()

    scheduled = await StatementRepository(statement_session).scheduled(
        user_id=user.id, filters=period(), projected_ranges={series_id: (11, 11)}
    )
    statement_session.expunge_all()
    dto = StatementEntrySchema.model_validate(scheduled[0][0])

    assert dto.subcategory is not None
    assert dto.subcategory_name == "Groceries"
    assert dto.category_name == "Essentials"
    assert dto.category_id == moved.subcategory.category_id
    assert dto.transaction_serie is not None
    assert dto.transaction_serie.subcategory is not None
    assert dto.transaction_serie.subcategory.id == entity.subcategory_id


@pytest.mark.asyncio
async def test_scheduled_without_subcategory_leaves_flat_fields_null(
    statement_session, user
):
    entity = make_series(user.id, subcategory_id=uuid4())
    moved = make_scheduled(entity, subcategory_id=None)
    statement_session.add_all([entity, moved])
    await statement_session.commit()
    series_id = entity.id
    statement_session.expunge_all()

    scheduled = await StatementRepository(statement_session).scheduled(
        user_id=user.id, filters=period(), projected_ranges={series_id: (11, 11)}
    )
    statement_session.expunge_all()
    dto = StatementEntrySchema.model_validate(scheduled[0][0])

    assert dto.subcategory is None
    assert dto.subcategory_name is None
    assert dto.category_id is None
    assert dto.category_name is None
    assert dto.transaction_serie is not None
    assert dto.transaction_serie.subcategory is not None


@pytest.mark.asyncio
async def test_statement_logs_and_surfaces_database_errors(user):
    repository = SimpleNamespace(
        series=AsyncMock(side_effect=RuntimeError("database down"))
    )
    with (
        patch(
            "app.domain.transaction.statement.service.log_service_success"
        ) as success,
        pytest.raises(HTTPException) as error,
    ):
        await StatementService(repository).list_all(user=user, page_filter=period())
    assert error.value.status_code == 500
    success.assert_not_called()
