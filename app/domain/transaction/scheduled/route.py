from __future__ import annotations
from typing import Annotated
from uuid import UUID
from http import HTTPStatus

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.transaction.scheduled.schema import (
    ScheduledTransactionSchema,
    ScheduledTransactionCreateSchema,
    ScheduledTransactionRequestCreateSchema, ScheduledTransactionRequestUpdateSchema
)
from app.domain.transaction.scheduled.service import ScheduledTransactionService
from app.models import User, TransactionDirectionEnum, TransactionStatusEnum
from app.shared.schemas import FilterPage, Message


router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]


def scheduled_transaction_service(session: Session) -> ScheduledTransactionService:
    return ScheduledTransactionService.from_session(session)


def scheduled_transaction_filter(
    page: int | None = None,
    name: str | None = None,
    status: TransactionStatusEnum | None = None,
    direction: TransactionDirectionEnum | None = None,
    limit: int | None = 12,
    offset: int | None = None,
    clean_cache: bool = False,
    transaction_series_id: UUID | None = None,
) -> FilterPage:
    return FilterPage.build(
        page=page,
        name=name,
        limit=limit,
        offset=offset,
        status=status,
        direction=direction,
        clean_cache=clean_cache,
        transaction_series_id=transaction_series_id
    )


Service = Annotated[ScheduledTransactionService, Depends(scheduled_transaction_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("/{transaction_series_id}", response_model=ScheduledTransactionSchema, status_code=HTTPStatus.CREATED)
async def create(
    service: Service,
    current_user: CurrentUser,
    transaction_series_id: UUID,
    transaction_data: ScheduledTransactionRequestCreateSchema,
):
    payload = ScheduledTransactionCreateSchema.model_validate(
        transaction_data.model_dump()
        | {"transaction_series_id": transaction_series_id}
    )
    return await service.create(user=current_user, payload=payload)


@router.get(
    "/{transaction_series_id}",
    response_model=CustomLimitOffsetPage[ScheduledTransactionSchema] | list[ScheduledTransactionSchema],
    status_code=HTTPStatus.OK,
)
async def list_all(
    service: Service,
    current_user: CurrentUser,
    transaction_series_id: UUID,
    page_filter: Annotated[FilterPage, Depends(scheduled_transaction_filter)],
):
    return await service.list_all(
        page_filter=FilterPage.build(
            page_filter=page_filter,
            transaction_series_id=transaction_series_id
        ),
        user=current_user,
    )


@router.get(
    "/{transaction_series_id}/{scheduled_transaction_id}",
    response_model=ScheduledTransactionSchema,
    status_code=HTTPStatus.OK,
)
async def find_one(
        transaction_series_id: UUID,
        scheduled_transaction_id: UUID,
        service: Service,
        current_user: CurrentUser
):
    return await service.find_by(
        filters={"id": scheduled_transaction_id, "transaction_series_id": transaction_series_id},
        user=current_user,
    )


@router.put(
    "/{transaction_series_id}/{scheduled_transaction_id}",
    response_model=Message,
    status_code=HTTPStatus.OK,
)
async def update(
    service: Service,
    transaction_series_id: UUID,
    scheduled_transaction_id: UUID,
    current_user: CurrentUser,
    payload: ScheduledTransactionRequestUpdateSchema,
):

    return await service.update_scheduled(
        identifier=scheduled_transaction_id,
        transaction_series_id=transaction_series_id,
        payload=payload,
        user=current_user
    )


@router.delete(
    "/{transaction_series_id}/{scheduled_transaction_id}",
    response_model=Message,
    status_code=HTTPStatus.OK,
)
async def delete(
    service: Service,
    transaction_series_id: UUID,
    scheduled_transaction_id: UUID,
    current_user: CurrentUser,
):
    return await service.delete_scheduled(
        user=current_user,
        identifier=scheduled_transaction_id,
        transaction_series_id=transaction_series_id
    )
