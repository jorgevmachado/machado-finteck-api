from __future__ import annotations

from datetime import datetime, date
from uuid import UUID, uuid4
from decimal import Decimal


from sqlalchemy import DateTime, ForeignKey, Numeric, Date, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import table_registry
from app.models import utcnow

@table_registry.mapped_as_dataclass
class Payment:
    __tablename__ = "payments"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    receipt_id: Mapped[UUID] = mapped_column(ForeignKey("receipts.id"), nullable=False)

    beneficiary_id: Mapped[UUID] = mapped_column(ForeignKey("beneficiaries.id"), nullable=False)

    subcategory_id: Mapped[UUID] = mapped_column(ForeignKey("subcategories.id"), nullable=False)

    source_institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"), nullable=False)

    payer_id: Mapped[UUID] = mapped_column(ForeignKey("payers.id"), nullable=False)

    payment_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    destination_institution_id: Mapped[UUID] = mapped_column(ForeignKey("institutions.id"), nullable=True)

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