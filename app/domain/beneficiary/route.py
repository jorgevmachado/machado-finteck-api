from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.beneficiary.schema import BeneficiaryCreateSchema, BeneficiarySchema, BeneficiaryUpdateSchema
from app.domain.beneficiary.service import BeneficiaryService
from app.models import User
from app.shared.schemas import FilterPage, Message

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]


def beneficiary_service(session: Session) -> BeneficiaryService:
    return BeneficiaryService.from_session(session)


def beneficiary_filter(
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


Service = Annotated[BeneficiaryService, Depends(beneficiary_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("", response_model=BeneficiarySchema, status_code=HTTPStatus.CREATED)
async def create(
    service: Service,
    current_user: CurrentUser,
    beneficiary_data: BeneficiaryCreateSchema,
):
    return await service.create(user=current_user, payload=beneficiary_data)


@router.get(
    "",
    response_model=CustomLimitOffsetPage[BeneficiarySchema] | list[BeneficiarySchema],
    status_code=HTTPStatus.OK,
)
async def list_all(
    service: Service,
    current_user: CurrentUser,
    page_filter: Annotated[FilterPage, Depends(beneficiary_filter)],
):
    return await service.list_all(page_filter=page_filter, user=current_user)


@router.get("/{beneficiary_id}", response_model=BeneficiarySchema, status_code=HTTPStatus.OK)
async def find_one(beneficiary_id: str, service: Service, current_user: CurrentUser):
    return await service.find_by(
        id=beneficiary_id,
        user_request=current_user.username,
        user_id=current_user.id,
    )


@router.put("/{beneficiary_id}", response_model=Message, status_code=HTTPStatus.OK)
async def update(
    service: Service,
    beneficiary_id: str,
    current_user: CurrentUser,
    payload: BeneficiaryUpdateSchema,
):
    return await service.update(beneficiary_id=beneficiary_id, payload=payload, user=current_user)


@router.delete("/{beneficiary_id}", response_model=Message, status_code=HTTPStatus.OK)
async def delete(service: Service, beneficiary_id: str, current_user: CurrentUser):
    return await service.delete(user=current_user, beneficiary_id=beneficiary_id)
