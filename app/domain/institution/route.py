from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.institution.schema import (
    InstitutionCreateSchema,
    InstitutionSchema,
    InstitutionUpdateSchema,
)
from app.domain.institution.service import InstitutionService
from app.models import User
from app.shared.schemas import FilterPage, Message

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]


def institution_service(session: Session) -> InstitutionService:
    return InstitutionService.from_session(session)


def institution_filter(
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


Service = Annotated[InstitutionService, Depends(institution_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("", response_model=InstitutionSchema, status_code=HTTPStatus.CREATED)
async def create(
    service: Service,
    current_user: CurrentUser,
    institution_data: InstitutionCreateSchema,
):
    return await service.create(user=current_user, payload=institution_data)


@router.get(
    "",
    response_model=CustomLimitOffsetPage[InstitutionSchema] | list[InstitutionSchema],
    status_code=HTTPStatus.OK,
)
async def list_all(
    service: Service,
    current_user: CurrentUser,
    page_filter: Annotated[FilterPage, Depends(institution_filter)],
):
    return await service.list_all(page_filter=page_filter, user=current_user)


@router.get(
    "/{institution_id}", response_model=InstitutionSchema, status_code=HTTPStatus.OK
)
async def find_one(institution_id: UUID, service: Service, current_user: CurrentUser):
    return await service.find_by(
        filters={"id": institution_id},
        user=current_user,
    )


@router.put("/{institution_id}", response_model=Message, status_code=HTTPStatus.OK)
async def update(
    service: Service,
    institution_id: UUID,
    current_user: CurrentUser,
    payload: InstitutionUpdateSchema,
):
    return await service.update(
        identifier=institution_id, payload=payload, user=current_user
    )


@router.delete("/{institution_id}", response_model=Message, status_code=HTTPStatus.OK)
async def delete(service: Service, institution_id: UUID, current_user: CurrentUser):
    return await service.delete(user=current_user, identifier=institution_id)
