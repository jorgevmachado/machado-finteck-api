from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4
from typing import TYPE_CHECKING


from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import table_registry, default_lazy
from app.models import utcnow

if TYPE_CHECKING:
    from app.models import Payment

@table_registry.mapped_as_dataclass
class Institution:
    __tablename__ = "institutions"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "name_code",
            name="uq_institutions_user_id_name_code",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Required fields (no defaults) — must come first in __init__
    name: Mapped[str] = mapped_column(String, nullable=False)

    name_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)

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

    source_payments: Mapped[list["Payment"]] = relationship(
        init=False,
        lazy=default_lazy,
        foreign_keys="Payment.source_institution_id",
        back_populates="source_institution",
    )

    destination_payments: Mapped[list["Payment"]] = relationship(
        init=False,
        lazy=default_lazy,
        foreign_keys="Payment.destination_institution_id",
        back_populates="destination_institution",
    )
