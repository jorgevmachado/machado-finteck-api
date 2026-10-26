from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user

from app.domain.receipt.payment.service import PaymentService
from app.domain.receipt.payment.schema import (
    PaymentSchema,
    PaymentDashboardResponseSchema,
    PaymentDashboardRequestSchema,
)

from app.models import User
from app.shared.schemas import FilterPage

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]

CurrentUser = Annotated[User, Depends(get_current_user)]


def payment_service(session: Session) -> PaymentService:
    return PaymentService.from_session(session)


def payment_filter(
    page: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1)] = 12,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FilterPage:
    return FilterPage.build(page=page, limit=limit, offset=offset)


Service = Annotated[PaymentService, Depends(payment_service)]


@router.get(
    "",
    response_model=CustomLimitOffsetPage[PaymentSchema] | list[PaymentSchema],
    status_code=HTTPStatus.OK,
)
async def list_all(
    service: Service,
    current_user: CurrentUser,
    page_filter: Annotated[FilterPage, Depends(payment_filter)],
):
    return await service.list_all(page_filter=page_filter, user=current_user)


@router.get(
    "/dashboard",
    response_model=PaymentDashboardResponseSchema,
    status_code=HTTPStatus.OK,
)
async def get_dashboard(
    params: Annotated[PaymentDashboardRequestSchema, Query()],
    service: Service,
    current_user: CurrentUser,
):
    return await service.get_dashboard(params=params, user=current_user)


@router.get("/{payment_id}", response_model=PaymentSchema, status_code=HTTPStatus.OK)
async def find_one(payment_id: UUID, service: Service, current_user: CurrentUser):
    return await service.find_one(payment_id=payment_id, user=current_user)
