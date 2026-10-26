from __future__ import annotations

from datetime import datetime, date
from uuid import UUID, uuid4
from decimal import Decimal
from typing import TYPE_CHECKING


from sqlalchemy import DateTime, ForeignKey, Numeric, Date, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import table_registry, default_lazy
from app.models import utcnow

if TYPE_CHECKING:
    from app.models import Receipt, Beneficiary, Subcategory, Institution, Payer


@table_registry.mapped_as_dataclass
class Payment:
    __tablename__ = "payments"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    receipt_id: Mapped[UUID] = mapped_column(ForeignKey("receipts.id"), nullable=False)

    receipt: Mapped["Receipt"] = relationship(
        init=False,
        lazy=default_lazy,
        back_populates="payments",
    )

    beneficiary_id: Mapped[UUID] = mapped_column(ForeignKey("beneficiaries.id"), nullable=False)

    beneficiary: Mapped["Beneficiary"] = relationship(
        init=False,
        lazy=default_lazy,
        back_populates="payments",
    )

    subcategory_id: Mapped[UUID] = mapped_column(ForeignKey("subcategories.id"), nullable=False)

    subcategory: Mapped["Subcategory"] = relationship(
        init=False,
        lazy=default_lazy,
        back_populates="payments",
    )

    source_institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"), nullable=False)

    source_institution: Mapped["Institution"] = relationship(
        init=False,
        lazy=default_lazy,
        foreign_keys=[source_institution_id],
        back_populates="source_payments",
    )

    payer_id: Mapped[UUID] = mapped_column(ForeignKey("payers.id"), nullable=False)

    payer: Mapped["Payer"] = relationship(
        init=False,
        lazy=default_lazy,
        back_populates="payments",
    )

    payment_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    destination_institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"), nullable=True)

    destination_institution: Mapped["Institution | None"] = relationship(
        init=False,
        lazy=default_lazy,
        foreign_keys=[destination_institution_id],
        back_populates="destination_payments",
    )

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    amount: Mapped[Decimal] = mapped_column(
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