from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import default_lazy, table_registry
from app.models import utcnow

if TYPE_CHECKING:
    from app.models.auth.user import User


@table_registry.mapped_as_dataclass
class Password:
    __tablename__ = "passwords"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    user: Mapped["User"] = relationship(
        init=False,
        lazy=default_lazy,
        back_populates="password",
    )

    # Required fields (no defaults) — must come first in __init__
    value: Mapped[str] = mapped_column(String, nullable=False)

    last_value: Mapped[str] = mapped_column(String, nullable=False)

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
