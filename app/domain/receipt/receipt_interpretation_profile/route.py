from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.receipt.receipt_interpretation_profile.schema import (
    ReceiptInterpretationProfileCreateSchema,
    ReceiptInterpretationProfileFilter,
    ReceiptInterpretationProfileSchema,
    ReceiptInterpretationProfileUpdateSchema,
)
from app.domain.receipt.receipt_interpretation_profile.service import (
    ReceiptInterpretationProfileService,
)
from app.models import User
from app.shared.schemas import Message

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
PageFilter = Annotated[ReceiptInterpretationProfileFilter, Query()]


def profile_service(session: Session) -> ReceiptInterpretationProfileService:
    return ReceiptInterpretationProfileService.from_session(session)


Service = Annotated[ReceiptInterpretationProfileService, Depends(profile_service)]


@router.post("", response_model=ReceiptInterpretationProfileSchema, status_code=201)
async def create(
    service: Service,
    current_user: CurrentUser,
    payload: ReceiptInterpretationProfileCreateSchema,
) -> ReceiptInterpretationProfileSchema:
    return await service.create(user=current_user, payload=payload)


@router.get(
    "",
    response_model=(
        CustomLimitOffsetPage[ReceiptInterpretationProfileSchema]
        | list[ReceiptInterpretationProfileSchema]
    ),
)
async def list_profiles(
    service: Service, current_user: CurrentUser, page_filter: PageFilter
):
    return await service.list_all(page_filter=page_filter, user=current_user)


@router.get("/{profile_id}", response_model=ReceiptInterpretationProfileSchema)
async def find_one(
    profile_id: UUID, service: Service, current_user: CurrentUser
) -> ReceiptInterpretationProfileSchema:
    return await service.find_by(profile_id=profile_id, user=current_user)


@router.put("/{profile_id}", response_model=Message)
async def update(
    profile_id: UUID,
    service: Service,
    current_user: CurrentUser,
    payload: ReceiptInterpretationProfileUpdateSchema,
) -> Message:
    return await service.update(
        profile_id=profile_id, payload=payload, user=current_user
    )


@router.delete("/{profile_id}", response_model=Message)
async def delete(
    profile_id: UUID, service: Service, current_user: CurrentUser
) -> Message:
    return await service.delete(profile_id=profile_id, user=current_user)
