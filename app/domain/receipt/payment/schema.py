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
