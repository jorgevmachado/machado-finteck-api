from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum as SAEnum, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import default_lazy, table_registry
from app.models.auth.enums import StatusEnum
from app.models import utcnow

if TYPE_CHECKING:
    from app.models.auth.role import Role
    from app.models.auth.password import Password
    from app.models.auth.authentication import Authentication


@table_registry.mapped_as_dataclass
class User:
    __tablename__ = "users"

    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id"), nullable=False)

    role: Mapped["Role"] = relationship(
        init=False,
        lazy=default_lazy,
        back_populates="users",
    )

    authentication: Mapped["Authentication"] = relationship(
        init=False,
        lazy=default_lazy,
        back_populates="user",
    )

    password: Mapped["Password"] = relationship(
        init=False,
        lazy=default_lazy,
        back_populates="user",
    )

    # Required fields (no defaults) — must come first in __init__
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    date_of_birth: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Optional fields with defaults
    status: Mapped[StatusEnum] = mapped_column(
        SAEnum(StatusEnum, name="statusenum"),
        nullable=False,
        default=StatusEnum.INACTIVE,
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
