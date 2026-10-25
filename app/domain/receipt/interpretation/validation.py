from __future__ import annotations

from app.domain.receipt.data.enums import DataStatusEnum
from app.domain.receipt.data.schema import ReceiptData, ReceiptDataError
from app.domain.receipt.interpretation.schema import InterpretationResult


class InterpretationValidator:
    REQUIRED_FIELDS = (
        "payment_date",
        "paid_amount",
        "beneficiary",
        "source_institution",
    )

    @classmethod
    def validate(
        cls,
        data: ReceiptData,
    ) -> InterpretationResult:
        errors = [
            ReceiptDataError(field=field_name, status=field.status)
            for field_name in cls.REQUIRED_FIELDS
            if (field := getattr(data, field_name)).status != DataStatusEnum.FOUND
        ]
        return InterpretationResult(
            data=data,
            errors=errors,
        )