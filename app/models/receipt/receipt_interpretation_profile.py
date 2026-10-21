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
    literal_column,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import table_registry
from app.models.common import utcnow

if TYPE_CHECKING:
    from app.models.receipt.receipt_field_rule import ReceiptFieldRule
    from app.models.receipt.receipt_identification_rule import ReceiptIdentificationRule


@table_registry.mapped_as_dataclass
class ReceiptInterpretationProfile:
    __tablename__ = "receipt_interpretation_profiles"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NULL AND institution_code IS NULL) OR "
            "(user_id IS NOT NULL AND institution_code IS NOT NULL)",
            name="ck_receipt_profiles_scope",
        ),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_receipt_profiles_name_nonempty",
        ),
        CheckConstraint(
            "institution_code IS NULL OR length(trim(institution_code)) > 0",
            name="ck_receipt_profiles_institution_nonempty",
        ),
        Index(
            "uq_receipt_profiles_general_live",
            literal_column("(1)"),
            unique=True,
            postgresql_where=text("user_id IS NULL AND deleted_at IS NULL"),
            sqlite_where=text("user_id IS NULL AND deleted_at IS NULL"),
        ),
        Index(
            "uq_receipt_profiles_owner_institution_live",
            "user_id",
            "institution_code",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL AND deleted_at IS NULL"),
            sqlite_where=text("user_id IS NOT NULL AND deleted_at IS NULL"),
        ),
    )

    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    name: Mapped[str] = mapped_column(String, nullable=False)

    institution_code: Mapped[str | None] = mapped_column(String, nullable=True)

    field_rules: Mapped[list["ReceiptFieldRule"]] = relationship(
        back_populates="profile",
        lazy="selectin",
        default_factory=list,
        init=False,
    )
    identification_rules: Mapped[list["ReceiptIdentificationRule"]] = relationship(
        back_populates="profile",
        lazy="selectin",
        default_factory=list,
        init=False,
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