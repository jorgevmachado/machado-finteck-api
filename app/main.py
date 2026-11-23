from http import HTTPStatus

from fastapi import FastAPI
from fastapi_pagination import add_pagination


from app.core.logging import configure_logging
from app.shared.schemas import Message, SeedSummarySchema
from app.seed import SeedRequestSchema, seed_all
from app.domain.account.route import Service as AccountServiceDependency, CurrentUser
from app.domain.credit_card.route import Service as CreditCardServiceDependency
from app.domain.institution.route import Service as InstitutionServiceDependency
from app.domain.category.route import Service as CategoryServiceDependency
from app.domain.transaction.route import Service as TransactionServiceDependency

from app.domain.auth.route import router as auth_router
from app.domain.account.route import router as account_router
from app.domain.payer.route import router as payer_router
from app.domain.credit_card.route import router as credit_card_router
from app.domain.category.route import router as category_router
from app.domain.beneficiary.route import router as beneficiary_router
from app.domain.institution.route import router as institution_router
from app.domain.receipt.route import router as receipt_router
from app.domain.transaction.route import router as transaction_router


configure_logging()
app = FastAPI()

add_pagination(app)

app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(account_router, prefix="/accounts", tags=["Accounts"])
app.include_router(payer_router, prefix="/payers", tags=["Payers"])
app.include_router(credit_card_router, prefix="/credit-cards", tags=["Credit Cards"])
app.include_router(category_router, prefix="/categories", tags=["Categories"])
app.include_router(beneficiary_router, prefix="/beneficiaries", tags=["Beneficiaries"])
app.include_router(institution_router, prefix="/institutions", tags=["Institutions"])
app.include_router(receipt_router, prefix="/receipts", tags=["Receipts"])
app.include_router(transaction_router, prefix="/transactions", tags=["Transactions"])


@app.post(
    "/seed", status_code=HTTPStatus.OK, response_model=SeedSummarySchema, tags=["Seed"]
)
async def seed(
    current_user: CurrentUser,
    accounts: AccountServiceDependency,
    credit_cards: CreditCardServiceDependency,
    institutions: InstitutionServiceDependency,
    categories: CategoryServiceDependency,
    transactions: TransactionServiceDependency,
    payload: SeedRequestSchema,
) -> SeedSummarySchema:
    return await seed_all(
        user=current_user,
        payload=payload,
        account_service=accounts,
        credit_card_service=credit_cards,
        institution_service=institutions,
        category_service=categories,
        transaction_service=transactions,
    )


@app.get("/", status_code=HTTPStatus.OK, response_model=Message)
def read_root():
    return {"message": "Hello World!"}
