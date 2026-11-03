from __future__ import annotations
from typing import Annotated
from uuid import UUID
from http import HTTPStatus

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.transaction.series.schema import (
    TransactionSeriesSchema,
    TransactionSeriesCreateSchema,
    TransactionSeriesUpdateSchema
)
from app.domain.transaction.series.service import TransactionSeriesService
from app.models import User, TransactionDirectionEnum, TransactionKindEnum, TransactionFrequencyUnitEnum
from app.shared.schemas import FilterPage, Message

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]


def transaction_series_service(session: Session) -> TransactionSeriesService:
    return TransactionSeriesService.from_session(session)


def transaction_series_filter(
    page: int | None = None,
    name: str | None = None,
    kind: TransactionKindEnum | None = None,
    direction: TransactionDirectionEnum | None = None,
    frequency_unit: TransactionFrequencyUnitEnum | None = None,
    limit: int | None = 12,
    offset: int | None = None,
    clean_cache: bool = False,
) -> FilterPage:
    return FilterPage.build(
        page=page,
        name=name,
        limit=limit,
        offset=offset,
        kind=kind,
        direction=direction,
        frequency_unit=frequency_unit,
        clean_cache=clean_cache,
    )


Service = Annotated[TransactionSeriesService, Depends(transaction_series_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("", response_model=TransactionSeriesSchema, status_code=HTTPStatus.CREATED)
async def create(
    service: Service,
    current_user: CurrentUser,
    transaction_series_data: TransactionSeriesCreateSchema,
):
    return await service.create(user=current_user, payload=transaction_series_data)


@router.get(
    "",
    response_model=CustomLimitOffsetPage[TransactionSeriesSchema] | list[TransactionSeriesSchema],
    status_code=HTTPStatus.OK,
)
async def list_all(
    service: Service,
    current_user: CurrentUser,
    page_filter: Annotated[FilterPage, Depends(transaction_series_filter)],
):
    return await service.list_all(
        page_filter=page_filter,
        user=current_user,
    )


@router.get(
    "/{transaction_series_id}",
    response_model=TransactionSeriesSchema,
    status_code=HTTPStatus.OK,
)
async def find_one(transaction_series_id: UUID, service: Service, current_user: CurrentUser):
    return await service.find_by(
        filters={"id": transaction_series_id},
        user=current_user,
    )


@router.put(
    "/{transaction_series_id}",
    response_model=Message,
    status_code=HTTPStatus.OK,
)
async def update(
    service: Service,
    transaction_series_id: UUID,
    current_user: CurrentUser,
    payload: TransactionSeriesUpdateSchema,
):
    return await service.update(
        identifier=transaction_series_id, payload=payload, user=current_user
    )


@router.delete(
    "/{transaction_series_id}",
    response_model=Message,
    status_code=HTTPStatus.OK,
)
async def delete(
    service: Service,
    transaction_series_id: UUID,
    current_user: CurrentUser,
):
    return await service.delete(user=current_user, identifier=transaction_series_id)
