from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.account.service import AccountService
from app.domain.category.service import CategoryService
from app.domain.credit_card.service import CreditCardService
from app.domain.institution.service import InstitutionService
from app.domain.transaction.schema import TransactionSeedRequestSchema
from app.domain.transaction.service import TransactionService
from app.models import User
from app.shared.schemas import SeedSummarySchema


class SeedTransactionsRequestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    one_offs: int = Field(default=100, ge=0, le=1000, strict=True)
    recurrences: int = Field(default=5, ge=0, le=100, strict=True)
    installment_plans: int = Field(default=5, ge=0, le=100, strict=True)
    months: int = Field(default=6, ge=1, le=24, strict=True)
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1, strict=True)

    @model_validator(mode="after")
    def require_quantity(self) -> "SeedTransactionsRequestSchema":
        if not (self.one_offs or self.recurrences or self.installment_plans):
            raise ValueError("At least one seed quantity must be positive")
        return self


class SeedRequestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transactions: SeedTransactionsRequestSchema = Field(
        default_factory=SeedTransactionsRequestSchema
    )


async def seed_all(
    *,
    user: User,
    payload: SeedRequestSchema,
    account_service: AccountService,
    credit_card_service: CreditCardService,
    institution_service: InstitutionService,
    category_service: CategoryService,
    transaction_service: TransactionService,
) -> SeedSummarySchema:
    accounts = await account_service.seed_defaults(user=user)
    credit_cards = await credit_card_service.seed_defaults(user=user)
    institutions = await institution_service.seed_defaults(user=user)
    subcategories_before = await category_service.count_subcategories(user=user)
    categories = await category_service.seed_defaults(user=user)
    subcategories_after = await category_service.count_subcategories(user=user)
    transactions = await transaction_service.seed(
        user=user,
        payload=TransactionSeedRequestSchema(
            transactions=payload.transactions.one_offs,
            recurrences=payload.transactions.recurrences,
            installment_plans=payload.transactions.installment_plans,
            months=payload.transactions.months,
            seed=payload.transactions.seed,
        ),
    )
    return SeedSummarySchema(
        account=accounts.created,
        credit_card=credit_cards.created,
        institution=institutions.created,
        category=categories.created,
        subcategory=subcategories_after - subcategories_before,
        transaction=transactions.transactions,
        transaction_series=transactions.transaction_series,
        scheduled_transaction=transactions.scheduled_transactions,
    )
