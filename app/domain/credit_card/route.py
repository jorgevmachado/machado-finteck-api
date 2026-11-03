from __future__ import annotations
from typing import Annotated
from uuid import UUID
from http import HTTPStatus

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.credit_card.schema import (
    CreditCardSchema,
    CreditCardCreateSchema,
    CreditCardUpdateSchema,
)
from app.domain.credit_card.service import CreditCardService
from app.models import CreditCardBrandEnum, User
from app.shared.schemas import FilterPage, Message

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]


def credit_card_service(session: Session) -> CreditCardService:
    return CreditCardService.from_session(session)


def credit_card_filter(
    page: int | None = None,
    name: str | None = None,
    brand: CreditCardBrandEnum | None = None,
    limit: int | None = 12,
    offset: int | None = None,
    is_active: bool | None = None,
    clean_cache: bool = False,
) -> FilterPage:
    return FilterPage.build(
        page=page,
        name=name,
        limit=limit,
        offset=offset,
        brand=brand,
        is_active=is_active,
        clean_cache=clean_cache,
    )


Service = Annotated[CreditCardService, Depends(credit_card_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("", response_model=CreditCardSchema, status_code=HTTPStatus.CREATED)
async def create(
    service: Service,
    current_user: CurrentUser,
    credit_card_data: CreditCardCreateSchema,
):
    return await service.create(user=current_user, payload=credit_card_data)


@router.get(
    "",
    response_model=CustomLimitOffsetPage[CreditCardSchema] | list[CreditCardSchema],
    status_code=HTTPStatus.OK,
)
async def list_all(
    service: Service,
    current_user: CurrentUser,
    page_filter: Annotated[FilterPage, Depends(credit_card_filter)],
):
    return await service.list_all(
        page_filter=page_filter,
        user=current_user,
    )


@router.get(
    "/{credit_card_id}",
    response_model=CreditCardSchema,
    status_code=HTTPStatus.OK,
)
async def find_one(credit_card_id: UUID, service: Service, current_user: CurrentUser):
    return await service.find_by(
        filters={"id": credit_card_id},
        user=current_user,
    )


@router.put(
    "/{credit_card_id}",
    response_model=Message,
    status_code=HTTPStatus.OK,
)
async def update(
    service: Service,
    credit_card_id: UUID,
    current_user: CurrentUser,
    payload: CreditCardUpdateSchema,
):
    return await service.update(
        identifier=credit_card_id, payload=payload, user=current_user
    )


@router.delete(
    "/{credit_card_id}",
    response_model=Message,
    status_code=HTTPStatus.OK,
)
async def delete(
    service: Service,
    credit_card_id: UUID,
    current_user: CurrentUser,
):
    return await service.delete(user=current_user, identifier=credit_card_id)
