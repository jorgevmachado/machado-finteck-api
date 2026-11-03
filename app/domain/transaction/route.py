from __future__ import annotations
from typing import Annotated
from uuid import UUID
from http import HTTPStatus

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.transaction.schema import (
    TransactionSchema,
    TransactionCreateSchema,
    TransactionUpdateSchema
)
from app.domain.transaction.service import TransactionService
from app.models import User, TransactionDirectionEnum, TransactionStatusEnum
from app.shared.schemas import FilterPage, Message

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]


def transaction_service(session: Session) -> TransactionService:
    return TransactionService.from_session(session)


def transaction_filter(
    page: int | None = None,
    name: str | None = None,
    status: TransactionStatusEnum | None = None,
    direction: TransactionDirectionEnum | None = None,
    limit: int | None = 12,
    offset: int | None = None,
    clean_cache: bool = False,
) -> FilterPage:
    return FilterPage.build(
        page=page,
        name=name,
        limit=limit,
        offset=offset,
        status=status,
        direction=direction,
        clean_cache=clean_cache,
    )


Service = Annotated[TransactionService, Depends(transaction_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("", response_model=TransactionSchema, status_code=HTTPStatus.CREATED)
async def create(
    service: Service,
    current_user: CurrentUser,
    transaction_data: TransactionCreateSchema,
):
    return await service.create(user=current_user, payload=transaction_data)


@router.get(
    "",
    response_model=CustomLimitOffsetPage[TransactionSchema] | list[TransactionSchema],
    status_code=HTTPStatus.OK,
)
async def list_all(
    service: Service,
    current_user: CurrentUser,
    page_filter: Annotated[FilterPage, Depends(transaction_filter)],
):
    return await service.list_all(
        page_filter=page_filter,
        user=current_user,
    )


@router.get(
    "/{transaction_id}",
    response_model=TransactionSchema,
    status_code=HTTPStatus.OK,
)
async def find_one(transaction_id: UUID, service: Service, current_user: CurrentUser):
    return await service.find_by(
        filters={"id": transaction_id},
        user=current_user,
    )


@router.put(
    "/{transaction_id}",
    response_model=Message,
    status_code=HTTPStatus.OK,
)
async def update(
    service: Service,
    transaction_id: UUID,
    current_user: CurrentUser,
    payload: TransactionUpdateSchema,
):
    return await service.update(
        identifier=transaction_id, payload=payload, user=current_user
    )


@router.delete(
    "/{transaction_id}",
    response_model=Message,
    status_code=HTTPStatus.OK,
)
async def delete(
    service: Service,
    transaction_id: UUID,
    current_user: CurrentUser,
):
    return await service.delete(user=current_user, identifier=transaction_id)
