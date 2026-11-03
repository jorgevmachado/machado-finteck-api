from __future__ import annotations

from builtins import list as List
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.category.schema import (
    CategoryCreateSchema,
    CategorySchema,
    CategorySeedSchema,
    CategoryUpdateSchema,
)
from app.domain.category.service import CategoryService
from app.models import Category, User
from app.shared.schemas import FilterPage, Message

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def category_service(session: Session) -> CategoryService:
    return CategoryService.from_session(session)


Service = Annotated[CategoryService, Depends(category_service)]


def category_filter(
    page: int | None = None,
    name: str | None = None,
    limit: int | None = 12,
    offset: int | None = None,
) -> FilterPage:
    return FilterPage.build(
        page=page,
        name=name,
        limit=limit,
        offset=offset,
    )


PageFilter = Annotated[FilterPage, Depends(category_filter)]


@router.post("", response_model=CategorySchema, status_code=HTTPStatus.CREATED)
async def create(
    service: Service,
    current_user: CurrentUser,
    payload: CategoryCreateSchema,
) -> Category:
    return await service.create(user=current_user, payload=payload)


@router.get(
    "",
    response_model=CustomLimitOffsetPage[CategorySchema] | List[CategorySchema],
    status_code=HTTPStatus.OK,
)
async def list_categories(
    service: Service,
    current_user: CurrentUser,
    page_filter: PageFilter,
) -> List[Category] | CustomLimitOffsetPage[Category]:
    return await service.list_all(page_filter=page_filter, user=current_user)


@router.post("/seed", response_model=CategorySeedSchema, status_code=HTTPStatus.OK)
async def seed(
    service: Service,
    current_user: CurrentUser,
) -> CategorySeedSchema:
    return await service.seed_defaults(user=current_user)


@router.get(
    "/{category_id}",
    response_model=CategorySchema,
    status_code=HTTPStatus.OK,
)
async def find_one(
    category_id: UUID,
    service: Service,
    current_user: CurrentUser,
):
    return await service.find_by(
        filters={"id": category_id},
        user=current_user,
    )


@router.put("/{category_id}", response_model=Message, status_code=HTTPStatus.OK)
async def update(
    category_id: UUID,
    service: Service,
    current_user: CurrentUser,
    payload: CategoryUpdateSchema,
) -> Message:
    return await service.update(
        identifier=category_id,
        payload=payload,
        user=current_user,
    )


@router.delete("/{category_id}", response_model=Message, status_code=HTTPStatus.OK)
async def delete(
    category_id: UUID,
    service: Service,
    current_user: CurrentUser,
) -> Message:
    return await service.delete(user=current_user, identifier=category_id)
