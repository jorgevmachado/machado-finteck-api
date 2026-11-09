from calendar import monthrange
from collections.abc import Iterable
from datetime import date, timedelta
from uuid import UUID

from app.domain.transaction.statement.schema import (
    StatementEntrySchema,
    StatementFilterSchema,
    StatementSeriesSchema,
)
from app.models import (
    TransactionFrequencyUnitEnum,
    TransactionKindEnum,
    TransactionStatusEnum,
)


def _month_date(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, monthrange(year, month)[1]))


def _month_at(anchor: date, months: int, day: int) -> date | None:
    year, month = divmod((anchor.year - 1) * 12 + anchor.month - 1 + months, 12)
    if year >= 9999:
        return None
    return _month_date(year + 1, month + 1, day)


def _first_occurrence(series: StatementSeriesSchema) -> date | None:
    start = series.start_date
    unit = series.frequency_unit
    if unit == TransactionFrequencyUnitEnum.WEEK:
        offset = ((series.week_day or start.isoweekday()) - start.isoweekday()) % 7
        if offset > (date.max - start).days:
            return None
        return start + timedelta(days=offset)
    day = series.day_of_month or start.day
    if unit == TransactionFrequencyUnitEnum.MONTH:
        candidate = _month_date(start.year, start.month, day)
        return candidate if candidate >= start else _month_at(start, 1, day)
    candidate = _month_date(start.year, series.month or start.month, day)
    if candidate >= start:
        return candidate
    if start.year == 9999:
        return None
    return _month_date(start.year + 1, series.month or start.month, day)


def _occurrence_at(
    series: StatementSeriesSchema, first: date, offset: int
) -> date | None:
    interval = series.frequency_interval
    if series.frequency_unit == TransactionFrequencyUnitEnum.WEEK:
        days = offset * interval * 7
        return first + timedelta(days=days) if days <= (date.max - first).days else None
    months = offset * interval
    if series.frequency_unit == TransactionFrequencyUnitEnum.YEAR:
        months *= 12
    return _month_at(first, months, series.day_of_month or series.start_date.day)


def project_series(
    series: StatementSeriesSchema, filters: StatementFilterSchema
) -> list[StatementEntrySchema]:
    first = _first_occurrence(series)
    if first is None:
        return []
    end = min(filters.end_date, series.end_date or filters.end_date)
    if first > end:
        return []
    if series.frequency_unit == TransactionFrequencyUnitEnum.WEEK:
        offset = max(
            0, (filters.start_date - first).days // (series.frequency_interval * 7)
        )
    else:
        months = (
            (filters.start_date.year - first.year) * 12
            + filters.start_date.month
            - first.month
        )
        step = series.frequency_interval * (
            12 if series.frequency_unit == TransactionFrequencyUnitEnum.YEAR else 1
        )
        offset = max(0, months // step)
    entries = []
    while series.kind != TransactionKindEnum.CLOSED or (
        series.installments is not None and offset < series.installments
    ):
        expected = _occurrence_at(series, first, offset)
        if expected is None or expected > end:
            break
        if expected >= filters.start_date:
            entries.append(
                StatementEntrySchema(
                    source="PROJECTED",
                    name=series.name,
                    note=series.note,
                    value=series.value,
                    direction=series.direction,
                    status=TransactionStatusEnum.PENDING,
                    expected_on=expected,
                    account=series.account,
                    credit_card=series.credit_card,
                    subcategory=series.subcategory,
                    transaction_series_id=series.id,
                    series_name=series.name,
                    series_kind=series.kind,
                    installments=series.installments,
                    occurrence_index=offset + 1,
                    occurrence_on=expected,
                )
            )
        offset += 1
    return entries


def _matches(entry: StatementEntrySchema, filters: StatementFilterSchema) -> bool:
    if not filters.start_date <= entry.expected_on <= filters.end_date:
        return False
    for relation, identifier in (
        (entry.account, filters.account_id),
        (entry.credit_card, filters.credit_card_id),
        (entry.subcategory, filters.subcategory_id),
    ):
        if identifier is not None and (relation is None or relation.id != identifier):
            return False
    for field in ("direction", "status"):
        value = getattr(filters, field)
        if value is not None and getattr(entry, field) != value:
            return False
    if filters.credit_card_id is None and filters.only_credit_card is not None:
        if (entry.credit_card is not None) != filters.only_credit_card:
            return False
    return filters.search is None or filters.search.casefold() in entry.name.casefold()


def combine_statement(
    *,
    transactions: Iterable[StatementEntrySchema],
    projections: Iterable[StatementEntrySchema],
    scheduled: Iterable[StatementEntrySchema],
    filters: StatementFilterSchema,
) -> list[StatementEntrySchema]:
    overrides: dict[tuple[UUID | None, int | None], StatementEntrySchema] = {}
    for entry in scheduled:
        key = (entry.transaction_series_id, entry.occurrence_index)
        if key in overrides:
            raise ValueError("Duplicate scheduled transactions for the same occurrence")
        overrides[key] = entry
    entries = [
        *transactions,
        *(
            entry
            for entry in projections
            if (entry.transaction_series_id, entry.occurrence_index) not in overrides
        ),
        *overrides.values(),
    ]
    priority = {"TRANSACTION": 0, "SCHEDULED": 1, "PROJECTED": 2}
    filtered = [entry for entry in entries if _matches(entry, filters)]
    filtered.sort(
        key=lambda entry: (
            priority[entry.source],
            str(entry.transaction_series_id or entry.id),
            entry.occurrence_index or 0,
        )
    )
    filtered.sort(
        key=lambda entry: getattr(entry, filters.order_by),
        reverse=filters.order == "desc",
    )
    return filtered
