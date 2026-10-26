from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.beneficiary.schema import BeneficiarySchema
from app.domain.category import SubcategorySchema
from app.domain.institution.schema import InstitutionSchema
from app.domain.payer.schema import PayerSchema
from app.domain.receipt.schema import ReceiptSchema


class PaymentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    amount: Decimal
    payer: PayerSchema
    receipt: ReceiptSchema
    subcategory: SubcategorySchema
    beneficiary: BeneficiarySchema
    payment_date: date
    source_institution: InstitutionSchema
    description: str | None = None
    destination_institution: InstitutionSchema | None = None
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class PaymentDashboardPeriodSchema(BaseModel):
    end_date: date
    start_date: date


class PaymentDashboardSummarySchema(BaseModel):
    total: Decimal
    count: int
    average: Decimal
    highest: Decimal


class PaymentDashboardMonthlySchema(BaseModel):
    total: Decimal
    count: int
    period: str


class PaymentDashboardInstitutionSchema(BaseModel):
    total: Decimal
    count: int
    institution: str


class PaymentDashboardBeneficiarySchema(BaseModel):
    name: str
    total: Decimal
    count: int
    beneficiary_id: UUID


class PaymentDashboardSubcategorySchema(BaseModel):
    name: str
    total: Decimal
    count: int
    subcategory_id: UUID


class PaymentDashboardPayerSchema(BaseModel):
    name: str
    total: Decimal
    count: int
    payer_id: UUID


class PaymentDashboardResponseSchema(BaseModel):
    payers: list[PaymentDashboardPayerSchema]
    period: PaymentDashboardPeriodSchema
    summary: PaymentDashboardSummarySchema
    monthly: list[PaymentDashboardMonthlySchema]
    subcategories: list[PaymentDashboardSubcategorySchema]
    institutions: list[PaymentDashboardInstitutionSchema]
    beneficiaries: list[PaymentDashboardBeneficiarySchema]


class PaymentDashboardRequestSchema(BaseModel):
    end_date: date
    start_date: date
    institution: str | None = None
    payer_id: UUID | None = None
    subcategory_id: UUID | None = None
    beneficiary_id: UUID | None = None
