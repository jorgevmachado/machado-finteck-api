from __future__ import annotations

from datetime import datetime, date
from uuid import UUID, uuid4
from decimal import Decimal
from typing import TYPE_CHECKING


from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, Enum as SAEnum, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import table_registry, default_lazy
from app.models import utcnow
from app.models.transaction.enums import TransactionDirectionEnum, TransactionStatusEnum

if TYPE_CHECKING:
    from app.models import Account, Subcategory, CreditCard, TransactionSeries


@table_registry.mapped_as_dataclass
class ScheduledTransaction:
    __tablename__ = "scheduled_transactions"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), nullable=False)

    account: Mapped["Account"] = relationship(
        init=False,
        lazy=default_lazy,
        back_populates="scheduled_transactions",
    )

    transaction_series_id: Mapped[UUID] = mapped_column(ForeignKey("transaction_series.id"), nullable=False)

    transaction_serie: Mapped["TransactionSeries"] = relationship(
        init=False,
        lazy=default_lazy,
        back_populates="scheduled_transactions",
    )

    subcategory_id: Mapped[UUID | None] = mapped_column(ForeignKey("subcategories.id"), nullable=True)

    subcategory: Mapped["Subcategory | None"] = relationship(
        init=False,
        lazy=default_lazy,
        back_populates="scheduled_transactions",
    )

    credit_card_id: Mapped[UUID | None] = mapped_column(ForeignKey("credit_cards.id"), nullable=True)

    credit_card: Mapped["CreditCard | None"] = relationship(
        init=False,
        lazy=default_lazy,
        back_populates="scheduled_transactions",
    )

    name: Mapped[str] = mapped_column(String, nullable=False)


    direction: Mapped[TransactionDirectionEnum] = mapped_column(
        SAEnum(TransactionDirectionEnum, name="transactiondirectionenum"), nullable=False
    )

    status: Mapped[TransactionStatusEnum] = mapped_column(
        SAEnum(TransactionStatusEnum, name="transactionstatusenum"), nullable=False
    )

    expected_on: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    settled_on: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    occurrence_on: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    occurrence_index: Mapped[int] = mapped_column(
        nullable=False,
    )

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