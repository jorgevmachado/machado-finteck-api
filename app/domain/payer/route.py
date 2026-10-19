from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.payer.schema import PayerCreateSchema, PayerSchema, PayerUpdateSchema
from app.domain.payer.service import PayerService
from app.models import User
from app.shared.schemas import FilterPage, Message

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]


def payer_service(session: Session) -> PayerService:
    return PayerService.from_session(session)


def payer_filter(
    page: int | None = None,
    name: str | None = None,
    limit: int | None = 12,
    offset: int | None = None,
    clean_cache: bool = False,
) -> FilterPage:
    return FilterPage.build(
        page=page,
        name=name,
        limit=limit,
        offset=offset,
        clean_cache=clean_cache,
    )


Service = Annotated[PayerService, Depends(payer_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("", response_model=PayerSchema, status_code=HTTPStatus.CREATED)
async def create(
    service: Service,
    current_user: CurrentUser,
    payer_data: PayerCreateSchema,
):
    return await service.create(user=current_user, payload=payer_data)


@router.get(
    "",
    response_model=CustomLimitOffsetPage[PayerSchema] | list[PayerSchema],
    status_code=HTTPStatus.OK,
)
async def list_all(
    service: Service,
    current_user: CurrentUser,
    page_filter: Annotated[FilterPage, Depends(payer_filter)],
):
    return await service.list_all(page_filter=page_filter, user=current_user)


@router.get("/{payer_id}", response_model=PayerSchema, status_code=HTTPStatus.OK)
async def find_one(payer_id: str, service: Service, current_user: CurrentUser):
    return await service.find_by(
        id=payer_id,
        user_request=current_user.username,
        user_id=current_user.id,
    )


@router.put("/{payer_id}", response_model=Message, status_code=HTTPStatus.OK)
async def update(
    service: Service,
    payer_id: str,
    current_user: CurrentUser,
    payload: PayerUpdateSchema,
):
    return await service.update(payer_id=payer_id, payload=payload, user=current_user)


@router.delete("/{payer_id}", response_model=Message, status_code=HTTPStatus.OK)
async def delete(service: Service, payer_id: str, current_user: CurrentUser):
    return await service.delete(user=current_user, payer_id=payer_id)
