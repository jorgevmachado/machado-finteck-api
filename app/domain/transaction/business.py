from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from random import Random
from uuid import UUID

from app.domain.transaction.scheduled.schema import (
    ScheduledTransactionRequestCreateSchema,
)
from app.domain.transaction.schema import (
    TransactionCreateSchema,
    TransactionSeedRequestSchema,
)
from app.domain.transaction.seeds import (
    InstallmentPlanSeedTemplate,
    RecurrenceSeedTemplate,
    SeedTemplate,
    TransactionSeedTemplate,
    TransactionSeedValueRange,
)
from app.domain.transaction.series.schema import TransactionSeriesCreateSchema
from app.models import (
    TransactionDirectionEnum,
    TransactionFrequencyUnitEnum,
    TransactionKindEnum,
    TransactionStatusEnum,
)


@dataclass
class SeedSeriesPlan:
    series: TransactionSeriesCreateSchema
    occurrences: list[ScheduledTransactionRequestCreateSchema]


@dataclass
class TransactionSeedPlan:
    start_date: date
    end_date: date
    transactions: list[TransactionCreateSchema]
    series: list[SeedSeriesPlan]


def _shift_month(value: date, offset: int) -> date:
    year, month = divmod(value.year * 12 + value.month - 1 + offset, 12)
    month += 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def _status(expected_on: date, today: date) -> TransactionStatusEnum:
    return (
        TransactionStatusEnum.SETTLED
        if expected_on < today
        else TransactionStatusEnum.PENDING
    )


def build_transaction_seed(
    *,
    payload: TransactionSeedRequestSchema,
    seed: int,
    today: date,
    templates: list[TransactionSeedTemplate],
    recurrence_templates: list[RecurrenceSeedTemplate],
    installment_templates: list[InstallmentPlanSeedTemplate],
    account_ids: list[UUID],
    credit_card_ids: list[UUID],
    subcategories: dict[str, UUID],
) -> TransactionSeedPlan:
    if not account_ids:
        raise ValueError("At least one account is required")
    random = Random(seed)
    start = _shift_month(today.replace(day=1), 1 - payload.months)
    end = today.replace(day=monthrange(today.year, today.month)[1])
    plan = TransactionSeedPlan(start, end, [], [])
    catalogs = {
        direction: [item for item in templates if item.direction == direction]
        for direction in TransactionDirectionEnum
    }

    def pick[TemplateT: SeedTemplate](catalog: list[TemplateT]) -> TemplateT:
        return random.choices(catalog, weights=[item.weight for item in catalog])[0]

    def money(value_range: TransactionSeedValueRange) -> Decimal:
        return Decimal(
            random.randint(int(value_range.min * 100), int(value_range.max * 100))
        ) / Decimal(100)

    def sample(
        template: SeedTemplate, direction: TransactionDirectionEnum, value: Decimal
    ) -> TransactionCreateSchema:
        expected = start + timedelta(days=random.randint(0, (end - start).days))
        return TransactionCreateSchema(
            name=template.name,
            value=value,
            direction=direction,
            account_id=random.choice(account_ids),
            credit_card_id=(
                random.choice(credit_card_ids)
                if direction == TransactionDirectionEnum.OUT
                and credit_card_ids
                and random.random() < 0.35
                else None
            ),
            subcategory_id=(
                subcategories.get(template.category_hint)
                if template.category_hint
                else None
            ),
            expected_on=expected,
            status=_status(expected, today),
            settled_on=expected if expected < today else None,
        )

    directions = [TransactionDirectionEnum.IN] * (payload.transactions * 15 // 100) + [
        TransactionDirectionEnum.OUT
    ] * (payload.transactions - payload.transactions * 15 // 100)
    random.shuffle(directions)
    for direction in directions:
        template = pick(catalogs[direction])
        plan.transactions.append(
            sample(template, direction, money(template.value_range))
        )
    for index in range(payload.recurrences + payload.installment_plans):
        closed = index >= payload.recurrences
        remainder = 0
        if closed:
            installment = pick(installment_templates)
            installments = random.randint(
                installment.installments_range.min, installment.installments_range.max
            )
            total = money(installment.total_range)
            cents, remainder = divmod(int(total * 100), installments)
            data = sample(
                installment, TransactionDirectionEnum.OUT, Decimal(cents) / Decimal(100)
            )
            unit = TransactionFrequencyUnitEnum.MONTH
        else:
            recurrence = pick(recurrence_templates)
            data = sample(
                recurrence, recurrence.direction, money(recurrence.value_range)
            )
            installments = None
            unit = recurrence.unit
        first = start + timedelta(days=random.randint(0, (today - start).days))
        last = _shift_month(first, installments - 1) if installments else None
        series = TransactionSeriesCreateSchema(
            **data.model_dump(exclude={"status", "settled_on", "expected_on"}),
            kind=TransactionKindEnum.CLOSED if closed else TransactionKindEnum.OPEN,
            start_date=first,
            end_date=last,
            installments=installments,
            frequency_unit=unit,
            frequency_interval=1,
            week_day=first.isoweekday()
            if unit == TransactionFrequencyUnitEnum.WEEK
            else None,
            day_of_month=first.day
            if unit != TransactionFrequencyUnitEnum.WEEK
            else None,
            month=first.month if unit == TransactionFrequencyUnitEnum.YEAR else None,
        )
        occurrences = []
        offset = 0
        while installments is None or offset < installments:
            if unit == TransactionFrequencyUnitEnum.WEEK:
                expected = first + timedelta(weeks=offset)
            else:
                expected = _shift_month(
                    first,
                    offset * (12 if unit == TransactionFrequencyUnitEnum.YEAR else 1),
                )
            if installments is None and expected > end:
                break
            occurrences.append(
                ScheduledTransactionRequestCreateSchema(
                    **data.model_dump(
                        exclude={"status", "settled_on", "expected_on", "value"}
                    ),
                    value=data.value
                    + (Decimal("0.01") if offset < remainder else Decimal(0)),
                    expected_on=expected,
                    occurrence_on=expected,
                    occurrence_index=offset + 1,
                    status=_status(expected, today),
                    settled_on=expected if expected < today else None,
                )
            )
            offset += 1
        plan.series.append(SeedSeriesPlan(series, occurrences))
    return plan
