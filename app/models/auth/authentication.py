from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import default_lazy, table_registry
from app.models import utcnow

if TYPE_CHECKING:
    from app.models.auth.user import User


@table_registry.mapped_as_dataclass
class Authentication:
    __tablename__ = "authentications"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    user: Mapped["User"] = relationship(
        init=False,
        lazy=default_lazy,
        back_populates="authentication",
    )

    # Required fields (no defaults) — must come first in __init__
    total: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    total_success: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    total_failures: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=0
    )
    failed_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    last_authentication_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
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
