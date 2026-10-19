from __future__ import annotations

from uuid import UUID, uuid4
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Enum as SAEnum, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import table_registry

from app.models import utcnow
from app.models.credit_card.enums import CreditCardBrandEnum


@table_registry.mapped_as_dataclass
class CreditCard:
    __tablename__ = "credit_cards"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    name: Mapped[str] = mapped_column(String, nullable=False)

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    brand: Mapped[CreditCardBrandEnum] = mapped_column(
        SAEnum(CreditCardBrandEnum, name="creditcardbrandenum"),
        nullable=False,
    )

    last_four_digits: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    closing_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    due_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    limit: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    color: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    icon: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
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
