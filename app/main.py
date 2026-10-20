from http import HTTPStatus

from fastapi import FastAPI
from fastapi_pagination import add_pagination


from app.core.logging import configure_logging
from app.shared.schemas import Message

from app.domain.auth.route import router as auth_router
from app.domain.account.route import router as account_router
from app.domain.payer.route import router as payer_router
from app.domain.credit_card.route import router as credit_card_router
from app.domain.category.route import router as category_router
from app.domain.beneficiary.route import router as beneficiary_router
from app.domain.institution.route import router as institution_router


configure_logging()
app = FastAPI()

add_pagination(app)

app.include_router(auth_router, prefix='/auth', tags=['Auth'])
app.include_router(account_router, prefix='/accounts', tags=['Accounts'])
app.include_router(payer_router, prefix="/payers", tags=["Payers"])
app.include_router(credit_card_router, prefix="/credit-cards", tags=["Credit Cards"])
app.include_router(category_router, prefix="/categories", tags=["Categories"])
app.include_router(beneficiary_router, prefix="/beneficiaries", tags=["Beneficiaries"])
app.include_router(institution_router, prefix="/institutions", tags=["Institutions"])
@app.get('/', status_code=HTTPStatus.OK, response_model=Message)
def read_root():
    return {'message': 'Hello World!'}
