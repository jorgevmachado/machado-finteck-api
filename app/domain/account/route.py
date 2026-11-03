from __future__ import annotations
from typing import Annotated
from uuid import UUID
from http import HTTPStatus

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.account.schema import (
    AccountSchema,
    AccountCreateSchema,
    AccountUpdateSchema,
)
from app.domain.account.service import AccountService
from app.models import AccountTypeEnum, User
from app.shared.schemas import FilterPage, Message

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]


def account_service(session: Session) -> AccountService:
    return AccountService.from_session(session)


def account_filter(
    type: AccountTypeEnum | None = None,
    page: int | None = None,
    name: str | None = None,
    limit: int | None = 12,
    offset: int | None = None,
    agency: str | None = None,
    is_active: bool | None = None,
    account_number: str | None = None,
    financial_institution: str | None = None,
    clean_cache: bool = False,
) -> FilterPage:
    return FilterPage.build(
        type=type,
        page=page,
        name=name,
        limit=limit,
        offset=offset,
        agency=agency,
        is_active=is_active,
        account_number=account_number,
        financial_institution=financial_institution,
        clean_cache=clean_cache,
    )


Service = Annotated[AccountService, Depends(account_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("", response_model=AccountSchema, status_code=HTTPStatus.CREATED)
async def create(
    service: Service,
    current_user: CurrentUser,
    account_data: AccountCreateSchema,
):
    return await service.create(user=current_user, payload=account_data)


@router.get(
    "",
    response_model=CustomLimitOffsetPage[AccountSchema] | list[AccountSchema],
    status_code=HTTPStatus.OK,
)
async def list_all(
    service: Service,
    current_user: CurrentUser,
    page_filter: Annotated[FilterPage, Depends(account_filter)],
):
    return await service.list_all(
        page_filter=page_filter,
        user=current_user,
    )


@router.get("/{account_id}", response_model=AccountSchema, status_code=HTTPStatus.OK)
async def find_one(account_id: UUID, service: Service, current_user: CurrentUser):
    return await service.find_by(
        filters={"id": account_id},
        user=current_user,
    )


@router.put(
    "/{account_id}",
    response_model=Message,
    status_code=HTTPStatus.OK,
)
async def update(
    service: Service,
    account_id: UUID,
    current_user: CurrentUser,
    payload: AccountUpdateSchema,
):
    return await service.update(
        identifier=account_id, payload=payload, user=current_user
    )


@router.delete(
    "/{account_id}",
    response_model=Message,
    status_code=HTTPStatus.OK,
)
async def delete(
    service: Service,
    account_id: UUID,
    current_user: CurrentUser,
):
    return await service.delete(user=current_user, identifier=account_id)
