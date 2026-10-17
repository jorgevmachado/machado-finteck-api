from http import HTTPStatus

from fastapi import FastAPI
from fastapi_pagination import add_pagination


from app.core.logging import configure_logging
from app.shared.schemas import Message

from app.domain.auth.route import router as auth_router
from app.domain.account.route import router as account_router



configure_logging()
app = FastAPI()

add_pagination(app)

app.include_router(auth_router, prefix='/auth', tags=['Auth'])
app.include_router(account_router, prefix='/accounts', tags=['Accounts'])

@app.get('/', status_code=HTTPStatus.OK, response_model=Message)
def read_root():
    return {'message': 'Hello World!'}
