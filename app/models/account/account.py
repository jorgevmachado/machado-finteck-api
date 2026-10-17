from __future__ import annotations

from uuid import UUID, uuid4
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Enum as SAEnum, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import table_registry

from app.models import utcnow
from app.models.account.enums import AccountTypeEnum

@table_registry.mapped_as_dataclass
class Account:
    __tablename__ = "accounts"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    name: Mapped[str] = mapped_column(String, nullable=False)

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    type: Mapped[AccountTypeEnum] = mapped_column(
        SAEnum(AccountTypeEnum, name="accounttypeenum"),
        nullable=False,
    )

    account_number: Mapped[str | None] =mapped_column(
        String,
        nullable=True,
    )

    agency: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    financial_institution: Mapped[str | None] = mapped_column(
        String,
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
