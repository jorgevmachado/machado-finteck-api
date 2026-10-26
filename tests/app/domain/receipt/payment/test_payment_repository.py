from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.domain.receipt.payment.repository import PaymentRepository
from app.shared.schemas import FilterPage

pytestmark = pytest.mark.asyncio


@pytest.fixture
def session():
    rows = Mock()
    rows.all.return_value = []
    rows.first.return_value = None
    return SimpleNamespace(
        scalars=AsyncMock(return_value=rows),
        execute=AsyncMock(),
    )


@pytest.fixture
def repository(session):
    return PaymentRepository(session)


def compile_query(query):
    return query.compile(dialect=postgresql.dialect())


def assert_owner_and_dates(query, user_id, start_date=None, end_date=None):
    compiled = compile_query(query)
    sql = str(compiled)
    assert "payments.user_id =" in sql
    assert user_id in compiled.params.values()
    if start_date is not None:
        assert "payments.payment_date >=" in sql
        assert start_date in compiled.params.values()
    if end_date is not None:
        assert "payments.payment_date <=" in sql
        assert end_date in compiled.params.values()


async def test_delete_removes_payment_then_commits(payment):
    session = AsyncMock()

    await PaymentRepository(session).delete(payment)

    session.delete.assert_awaited_once_with(payment)
    session.commit.assert_awaited_once_with()
    assert session.mock_calls == [call.delete(payment), call.commit()]


@pytest.mark.parametrize("failed_method", ["delete", "commit"])
async def test_delete_propagates_database_errors(payment, failed_method):
    session = AsyncMock()
    getattr(session, failed_method).side_effect = RuntimeError("database failure")

    with pytest.raises(RuntimeError, match="database failure"):
        await PaymentRepository(session).delete(payment)

    session.delete.assert_awaited_once_with(payment)
    if failed_method == "delete":
        session.commit.assert_not_awaited()
    else:
        session.commit.assert_awaited_once_with()


@pytest.mark.parametrize("page_filter", [None, FilterPage()])
async def test_list_scopes_owner_and_loads_existing_relationships(
    repository, session, user, payment, page_filter
):
    session.scalars.return_value.all.return_value = [payment]

    result = await repository.list(user.id, page_filter)

    assert result == [payment]
    session.scalars.assert_awaited_once()
    query = session.scalars.await_args.args[0]
    assert_owner_and_dates(query, user.id)
    loader_names = {option.path.path[1].key for option in query._with_options}
    assert loader_names == {
        "beneficiary",
        "subcategory",
        "payer",
        "source_institution",
        "destination_institution",
    }
    assert "ORDER BY" not in str(compile_query(query))


@pytest.mark.parametrize(
    ("filters", "column", "direction"),
    [
        ({"order_by": "payment_date", "order": "asc"}, "payment_date", "ASC"),
        ({"order_by": "amount", "order": "desc"}, "amount", "DESC"),
        ({"order_by": "amount"}, "amount", "DESC"),
        ({"order": "asc"}, "created_at", "ASC"),
        ({"order_by": "unknown", "order": "desc"}, "created_at", "DESC"),
    ],
)
async def test_list_orders_by_supported_columns(
    repository, session, user, filters, column, direction
):
    await repository.list(user.id, FilterPage.build(**filters))

    sql = str(compile_query(session.scalars.await_args.args[0]))
    assert f"ORDER BY payments.{column} {direction}" in sql


@pytest.mark.parametrize(
    ("relation", "name", "table", "field", "expected"),
    [
        ("payer", "  Electric Company  ", "payers", "name_code", "electric_company"),
        (
            "beneficiary",
            "  Water Company  ",
            "beneficiaries",
            "name_code",
            "water_company",
        ),
        (
            "subcategory",
            "  Super   Mercado  ",
            "subcategories",
            "name",
            "Super Mercado",
        ),
        (
            "source_institution",
            "  Source Bank  ",
            "institutions",
            "name_code",
            "source_bank",
        ),
        (
            "destination_institution",
            "  Destination Bank  ",
            "institutions",
            "name_code",
            "destination_bank",
        ),
    ],
)
async def test_list_filters_named_relationships(
    repository, session, user, relation, name, table, field, expected
):
    await repository.list(user.id, FilterPage.build(**{relation: name}))

    compiled = compile_query(session.scalars.await_args.args[0])
    sql = str(compiled)
    assert f"JOIN {table} AS {table}_1" in sql
    assert f"{table}_1.{field} =" in sql
    assert expected in compiled.params.values()
    assert_owner_and_dates(session.scalars.await_args.args[0], user.id)


async def test_list_uses_independent_aliases_for_source_and_destination(
    repository, session, user
):
    await repository.list(
        user.id,
        FilterPage.build(
            source_institution="Source Bank",
            destination_institution="Destination Bank",
        ),
    )

    compiled = compile_query(session.scalars.await_args.args[0])
    sql = str(compiled)
    assert "institutions_1.id = payments.destination_institution_id" in sql
    assert "institutions_2.id = payments.source_institution_id" in sql
    assert "institutions_1.name_code =" in sql
    assert "institutions_2.name_code =" in sql
    assert "source_bank" in compiled.params.values()
    assert "destination_bank" in compiled.params.values()


@pytest.mark.parametrize("bounds", ["start", "end", "both"])
async def test_list_applies_inclusive_date_bounds(repository, session, user, bounds):
    start = date(2026, 1, 1) if bounds != "end" else None
    end = date(2026, 12, 31) if bounds != "start" else None
    page_filter = FilterPage.build(start_date=start, end_date=end)
    original = page_filter.model_dump()

    await repository.list(user.id, page_filter)

    assert_owner_and_dates(session.scalars.await_args.args[0], user.id, start, end)
    assert page_filter.model_dump() == original


@pytest.mark.parametrize(
    "page_filter",
    [FilterPage(limit=2, offset=4), FilterPage(limit=2, page=2)],
)
async def test_list_delegates_pagination_with_filtered_ordered_query(
    repository, session, user, page_filter
):
    repository.list_paginate = AsyncMock()

    result = await repository.list(user.id, page_filter)

    assert result is repository.list_paginate.return_value
    repository.list_paginate.assert_awaited_once()
    query, actual_filter = repository.list_paginate.await_args.args
    assert actual_filter is page_filter
    assert_owner_and_dates(query, user.id)
    session.scalars.assert_not_awaited()


@pytest.mark.parametrize(
    "method", ["summary_count", "summary_total", "summary_beneficiary"]
)
@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("filtered", [False, True])
async def test_summaries_aggregate_results_and_keep_only_date_filters(
    repository, session, user, method, empty, filtered
):
    amounts = (
        []
        if empty
        else [
            SimpleNamespace(amount=Decimal("10.10")),
            SimpleNamespace(amount=Decimal("20.20")),
        ]
    )
    session.scalars.return_value.all.return_value = amounts
    start, end = date(2026, 1, 1), date(2026, 12, 31)
    page_filter = (
        FilterPage.build(
            start_date=start,
            end_date=end,
            payer="Ignored Payer",
            source_institution="Ignored Bank",
            limit=1,
            offset=0,
        )
        if filtered
        else None
    )
    kwargs = (
        {"beneficiary": "  Water Company  "} if method == "summary_beneficiary" else {}
    )

    result = await getattr(repository, method)(
        user.id, page_filter=page_filter, **kwargs
    )

    total = Decimal("0") if empty else Decimal("30.30")
    expected = (
        {"count": len(amounts)} if method == "summary_count" else {"total": total}
    )
    if method == "summary_beneficiary":
        expected["beneficiary"] = "  Water Company  "
    assert result == expected
    query = session.scalars.await_args.args[0]
    assert_owner_and_dates(
        query,
        user.id,
        start if filtered else None,
        end if filtered else None,
    )
    compiled = compile_query(query)
    assert "ignored_payer" not in compiled.params.values()
    assert "ignored_bank" not in compiled.params.values()
    assert "LIMIT" not in str(compiled)
    if method == "summary_beneficiary":
        assert "JOIN beneficiaries" in str(compiled)
        assert "water_company" in compiled.params.values()
    else:
        assert "JOIN" not in str(compiled)
    if filtered:
        assert page_filter.limit == 1
        assert page_filter.payer == "Ignored Payer"


@pytest.mark.parametrize("direction", [None, "asc", "desc"])
@pytest.mark.parametrize("empty", [False, True])
async def test_summary_order_returns_extreme_payment(
    repository, session, user, payment, direction, empty
):
    expected = None if empty else payment
    session.scalars.return_value.first.return_value = expected
    start, end = date(2026, 1, 1), date(2026, 12, 31)

    result = await repository.summary_order_by(
        user.id,
        direction,
        FilterPage.build(start_date=start, end_date=end, payer="Ignored"),
    )

    assert result is expected
    query = session.scalars.await_args.args[0]
    compiled = compile_query(query)
    order = "ASC" if direction == "asc" else "DESC"
    assert f"ORDER BY payments.amount {order}" in str(compiled)
    assert compiled.params["param_1"] == 1
    assert "ignored" not in compiled.params.values()
    assert_owner_and_dates(query, user.id, start, end)


@pytest.mark.parametrize("filtered", [False, True])
async def test_dashboard_summary_returns_aggregates_and_scopes_query(
    repository, session, user, filtered
):
    row = SimpleNamespace(
        count=2,
        total=Decimal("30.30"),
        average=Decimal("15.15"),
        highest=Decimal("20.20"),
    )
    session.execute.return_value = Mock()
    session.execute.return_value.one.return_value = row
    start, end = date(2026, 1, 1), date(2026, 12, 31)
    beneficiary_id = uuid4()
    filters = (
        {"institution": "Source Bank", "beneficiary_id": beneficiary_id}
        if filtered
        else {}
    )

    result = await repository.dashboard_summary(user.id, start, end, **filters)

    assert result == vars(row)
    query = session.execute.await_args.args[0]
    compiled = compile_query(query)
    sql = str(compiled)
    assert "count(payments.id)" in sql
    assert "sum(payments.amount)" in sql
    assert "round(avg(payments.amount)" in sql
    assert "max(payments.amount)" in sql
    assert sql.count("coalesce(") == 3
    assert_owner_and_dates(query, user.id, start, end)
    if filtered:
        assert "source_bank" in compiled.params.values()
        assert beneficiary_id in compiled.params.values()
    else:
        assert "JOIN" not in sql


@pytest.mark.parametrize(
    ("method", "id_field", "group_table", "label", "filter_field"),
    [
        ("dashboard_monthly", None, None, "period", "beneficiary_id"),
        (
            "dashboard_institutions",
            "institution_id",
            "institutions",
            "institution",
            "beneficiary_id",
        ),
        (
            "dashboard_beneficiaries",
            "beneficiary_id",
            "beneficiaries",
            "name",
            "beneficiary_id",
        ),
        (
            "dashboard_categories",
            "subcategory_id",
            "subcategories",
            "name",
            "category_id",
        ),
        ("dashboard_payers", "payer_id", "payers", "name", "payer_id"),
    ],
)
@pytest.mark.parametrize("empty", [False, True])
async def test_dashboard_groups_serialize_rows_and_apply_optional_filters(
    repository, session, user, method, id_field, group_table, label, filter_field, empty
):
    values = {
        label: "2026-01" if label == "period" else "Group",
        "count": 2,
        "total": Decimal("30.30"),
    }
    if id_field is not None:
        values[id_field] = uuid4()
    session.execute.return_value = [] if empty else [SimpleNamespace(**values)]
    start, end = date(2026, 1, 1), date(2026, 12, 31)
    identifier = uuid4()

    result = await getattr(repository, method)(
        user.id, start, end, institution="Source Bank", **{filter_field: identifier}
    )

    assert result == ([] if empty else [values])
    query = session.execute.await_args.args[0]
    compiled = compile_query(query)
    sql = str(compiled)
    assert_owner_and_dates(query, user.id, start, end)
    assert identifier in compiled.params.values()
    assert "source_bank" in compiled.params.values()
    expected_field = "subcategory_id" if filter_field == "category_id" else filter_field
    assert f"payments.{expected_field} =" in sql
    assert "GROUP BY" in sql
    if method == "dashboard_monthly":
        assert "to_char(payments.payment_date" in sql
        assert "YYYY-MM" in compiled.params.values()
        assert "ORDER BY period" in sql
    else:
        assert f"JOIN {group_table}" in sql
        assert f"{group_table}.id" in sql
        assert "ORDER BY sum(payments.amount) DESC" in sql


@pytest.mark.parametrize(
    "method",
    [
        "list",
        "summary_count",
        "summary_total",
        "summary_order_by",
        "summary_beneficiary",
        "dashboard_summary",
        "dashboard_monthly",
        "dashboard_institutions",
        "dashboard_beneficiaries",
        "dashboard_categories",
        "dashboard_payers",
    ],
)
async def test_query_methods_propagate_database_errors(
    repository, session, user, method
):
    session.scalars.side_effect = RuntimeError("database failure")
    session.execute.side_effect = RuntimeError("database failure")
    kwargs = {}
    if method.startswith("dashboard"):
        kwargs.update(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    if method == "summary_beneficiary":
        kwargs["beneficiary"] = "Water Company"

    with pytest.raises(RuntimeError, match="database failure"):
        await getattr(repository, method)(user.id, **kwargs)
