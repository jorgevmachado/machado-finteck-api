from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Boolean, String, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import table_registry
from app.models.common import utcnow

if TYPE_CHECKING:
    from app.models.receipt.receipt_interpretation_profile import (
        ReceiptInterpretationProfile,
    )


@table_registry.mapped_as_dataclass
class ReceiptIdentificationRule:
    __tablename__ = "receipt_identification_rules"
    __table_args__ = (
        CheckConstraint(
            "length(trim(pattern)) > 0",
            name="ck_receipt_identification_pattern_nonempty",
        ),
        CheckConstraint("weight > 0", name="ck_receipt_identification_weight_positive"),
    )

    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("receipt_interpretation_profiles.id"),
        nullable=False,
    )

    profile: Mapped["ReceiptInterpretationProfile"] = relationship(
        back_populates="identification_rules",
        init=False,
        repr=False,
    )

    pattern: Mapped[str] = mapped_column(String, nullable=False)

    weight: Mapped[int] = mapped_column(Integer, nullable=False)

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
