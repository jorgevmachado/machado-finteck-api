from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.receipt.payment.repository import PaymentRepository
from app.domain.receipt.payment.service import PaymentService
from app.domain.receipt.payment.schema import PaymentDashboardRequestSchema
from app.models import Payment, ReceiptStatusEnum, utcnow


@pytest.fixture
def payment_values():
    return {
        "payer_id": uuid4(),
        "receipt_id": uuid4(),
        "amount": Decimal("123.45"),
        "payment_date": date(2026, 10, 26),
        "beneficiary_id": uuid4(),
        "subcategory_id": uuid4(),
        "source_institution_id": uuid4(),
        "description": "Monthly payment",
        "destination_institution_id": uuid4(),
    }


@pytest.fixture
def payment(user, payment_values):
    return Payment(user_id=user.id, **payment_values)


@pytest.fixture
def payment_repository():
    repository = AsyncMock(spec=PaymentRepository)
    repository.find_by.return_value = None
    repository.save.side_effect = lambda *, entity: entity
    return repository


@pytest.fixture
def payment_service(payment_repository):
    return PaymentService(payment_repository)


@pytest.fixture
def payment_output(payment):
    def named_entity(identifier, name):
        return SimpleNamespace(id=identifier, name=name, created_at=utcnow())

    return SimpleNamespace(
        id=payment.id,
        amount=payment.amount,
        payer=named_entity(payment.payer_id, "Payer"),
        receipt=SimpleNamespace(
            id=payment.receipt_id,
            status=ReceiptStatusEnum.PROCESSED,
            file_name="receipt.pdf",
            file_type="application/pdf",
            file_size=7,
            created_at=utcnow(),
        ),
        subcategory=SimpleNamespace(
            id=payment.subcategory_id,
            name="Groceries",
            icon=None,
            color=None,
            is_active=True,
            order=1,
            created_at=utcnow(),
        ),
        beneficiary=named_entity(payment.beneficiary_id, "Beneficiary"),
        payment_date=payment.payment_date,
        source_institution=named_entity(payment.source_institution_id, "Source"),
        description=payment.description,
        destination_institution=named_entity(
            payment.destination_institution_id, "Destination"
        ),
        created_at=payment.created_at,
    )


@pytest.fixture
def dashboard_params():
    return PaymentDashboardRequestSchema(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        institution="Source Bank",
        beneficiary_id=uuid4(),
        subcategory_id=uuid4(),
        payer_id=uuid4(),
    )


@pytest.fixture
def dashboard_data():
    return {
        "summary": {
            "total": Decimal("123.45"),
            "count": 1,
            "average": Decimal("123.45"),
            "highest": Decimal("123.45"),
        },
        "monthly": [{"period": "2026-10", "total": Decimal("123.45"), "count": 1}],
        "institutions": [
            {"institution": "source_bank", "total": Decimal("123.45"), "count": 1}
        ],
        "beneficiaries": [
            {
                "beneficiary_id": uuid4(),
                "name": "Beneficiary",
                "total": Decimal("123.45"),
                "count": 1,
            }
        ],
        "subcategories": [
            {
                "subcategory_id": uuid4(),
                "name": "Groceries",
                "total": Decimal("123.45"),
                "count": 1,
            }
        ],
        "payers": [
            {
                "payer_id": uuid4(),
                "name": "Payer",
                "total": Decimal("123.45"),
                "count": 1,
            }
        ],
    }


@pytest.fixture
def dashboard_response(dashboard_data, dashboard_params):
    return {
        **dashboard_data,
        "period": {
            "start_date": dashboard_params.start_date,
            "end_date": dashboard_params.end_date,
        },
    }
