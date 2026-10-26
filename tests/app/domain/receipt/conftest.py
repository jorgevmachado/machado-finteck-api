from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.receipt.schema import ReceiptConfirmSchema


@pytest.fixture
def confirm_payload():
    return ReceiptConfirmSchema(
        payer="Payer",
        beneficiary="Beneficiary",
        paid_amount=Decimal("123.45"),
        payment_date=date(2026, 10, 26),
        subcategory_id=uuid4(),
        source_institution="Source bank",
        destination_institution="Destination bank",
        description="Monthly payment",
    )
