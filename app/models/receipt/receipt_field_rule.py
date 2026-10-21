from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Boolean, String, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database.base import table_registry
from app.models.common import utcnow

if TYPE_CHECKING:
    from app.models.receipt.receipt_interpretation_profile import (
        ReceiptInterpretationProfile,
    )


@table_registry.mapped_as_dataclass
class ReceiptFieldRule:
    __tablename__ = "receipt_field_rules"
    __table_args__ = (
        CheckConstraint(
            "length(trim(field_name)) > 0",
            name="ck_receipt_field_rules_field_nonempty",
        ),
        CheckConstraint(
            "jsonb_typeof(configuration) = 'object' AND configuration <> '{}'::jsonb",
            name="ck_receipt_field_rules_configuration_object",
        ).ddl_if(dialect="postgresql"),
        Index(
            "uq_receipt_field_rules_profile_field_live",
            "profile_id",
            "field_name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("receipt_interpretation_profiles.id"),
        nullable=False,
    )

    profile: Mapped["ReceiptInterpretationProfile"] = relationship(
        back_populates="field_rules",
        init=False,
        repr=False,
    )

    field_name: Mapped[str] = mapped_column(String, nullable=False)

    configuration: Mapped[dict[str, object]] = mapped_column(
        JSONB(none_as_null=True),
        nullable=False,
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
