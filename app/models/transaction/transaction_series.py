from __future__ import annotations

from datetime import datetime, date
from uuid import UUID, uuid4
from decimal import Decimal
from typing import TYPE_CHECKING


from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, Enum as SAEnum, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import table_registry, default_lazy
from app.models import utcnow
from app.models.transaction.enums import TransactionDirectionEnum, TransactionKindEnum, \
    TransactionFrequencyUnitEnum

if TYPE_CHECKING:
    from app.models import Account, Subcategory, CreditCard, ScheduledTransaction


@table_registry.mapped_as_dataclass
class TransactionSeries:
    __tablename__ = "transaction_series"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), nullable=False)

    account: Mapped["Account"] = relationship(
        init=False,
        lazy=default_lazy,
        back_populates="transaction_series",
    )

    subcategory_id: Mapped[UUID | None] = mapped_column(ForeignKey("subcategories.id"), nullable=True)

    subcategory: Mapped["Subcategory | None"] = relationship(
        init=False,
        lazy=default_lazy,
        back_populates="transaction_series",
    )

    credit_card_id: Mapped[UUID | None] = mapped_column(ForeignKey("credit_cards.id"), nullable=True)

    credit_card: Mapped["CreditCard | None"] = relationship(
        init=False,
        lazy=default_lazy,
        back_populates="transaction_series",
    )

    name: Mapped[str] = mapped_column(String, nullable=False)

    kind: Mapped[TransactionKindEnum] = mapped_column(
        SAEnum(TransactionKindEnum, name="transactionkindenum"), nullable=False
    )

    frequency_unit: Mapped[TransactionFrequencyUnitEnum] = mapped_column(
        SAEnum(TransactionFrequencyUnitEnum, name="transactionfrequencyunitenum"), nullable=False
    )

    direction: Mapped[TransactionDirectionEnum] = mapped_column(
        SAEnum(TransactionDirectionEnum, name="transactiondirectionenum"), nullable=False
    )

    frequency_interval: Mapped[int] = mapped_column(
        nullable=False,
    )

    week_day: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    day_of_month: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    month: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    installments: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    value: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    # Auto-generated / server-managed — excluded from __init__
    id: Mapped[UUID] = mapped_column(
        primary_key=True, default_factory=uuid4, init=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default_factory=utcnow, init=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, init=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, init=False
    )

    scheduled_transactions: Mapped[list["ScheduledTransaction"]] = relationship(
        lazy=default_lazy,
        default_factory=list,
        init=False,
        repr=False,
        back_populates="transaction_serie",
    )