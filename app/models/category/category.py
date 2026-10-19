from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import table_registry
from app.models.common import utcnow

if TYPE_CHECKING:
    from app.models.category.subcategory import Subcategory


@table_registry.mapped_as_dataclass
class Category:
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="ck_categories_name_nonempty"),
        CheckConstraint(
            "color IS NULL OR color ~ '^#[0-9A-Fa-f]{6}$'",
            name="ck_categories_color_hex",
        ),
        Index(
            "uq_categories_owner_name_live",
            "user_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("ix_categories_user_id_deleted_at", "user_id", "deleted_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", name="fk_categories_user_id_users"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(collation="C"), nullable=False)
    icon: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    color: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    subcategories: Mapped[list["Subcategory"]] = relationship(
        back_populates="category",
        init=False,
        default_factory=list,
        order_by="Subcategory.order",
        lazy="selectin",
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default_factory=uuid4, init=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default_factory=utcnow, init=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        onupdate=utcnow,
        init=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, init=False
    )
