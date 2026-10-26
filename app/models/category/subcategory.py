from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import table_registry, default_lazy
from app.models.common import utcnow

if TYPE_CHECKING:
    from app.models.category.category import Category
    from app.models import Payment


@table_registry.mapped_as_dataclass
class Subcategory:
    __tablename__ = "subcategories"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(name)) > 0", name="ck_subcategories_name_nonempty"
        ),
        CheckConstraint(
            "color IS NULL OR color ~ '^#[0-9A-Fa-f]{6}$'",
            name="ck_subcategories_color_hex",
        ),
        CheckConstraint('"order" > 0', name="ck_subcategories_order_positive"),
        Index("ix_subcategories_category_id", "category_id"),
        UniqueConstraint(
            "category_id",
            "live_order",
            name="uq_subcategories_category_live_order",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    name: Mapped[str] = mapped_column(String(collation="C"), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    icon: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    color: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    category_id: Mapped[UUID] = mapped_column(
        ForeignKey("categories.id", name="fk_subcategories_category_id_categories"),
        nullable=False,
        init=False,
    )
    category: Mapped["Category"] = relationship(
        back_populates="subcategories",
        init=False,
    )

    live_order: Mapped[int | None] = mapped_column(
        Integer,
        Computed(
            'CASE WHEN deleted_at IS NULL THEN "order" ELSE NULL END',
            persisted=True,
        ),
        nullable=True,
        init=False,
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

    payments: Mapped[list["Payment"]] = relationship(
        lazy=default_lazy,
        default_factory=list,
        init=False,
        repr=False,
        back_populates="subcategory",
    )
