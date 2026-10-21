from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.receipt.rules.schema import ReceiptRulesSchema, ReceiptRulesCreateSchema, ReceiptRulesFilter, \
    ReceiptRulesUpdateSchema, ReceiptRulesSeedSchema
from app.domain.receipt.rules.service import ReceiptRulesService
from app.models import User
from app.shared.schemas import Message

router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
PageFilter = Annotated[ReceiptRulesFilter, Query()]

def receipt_rule_service(session: Session) -> ReceiptRulesService:
    return ReceiptRulesService.from_session(session)


Service = Annotated[ReceiptRulesService, Depends(receipt_rule_service)]
@router.post("", response_model=ReceiptRulesSchema, status_code=HTTPStatus.CREATED)
async def create(
    service: Service,
    current_user: CurrentUser,
    payload: ReceiptRulesCreateSchema,
) -> ReceiptRulesSchema:
    return await service.create(user=current_user, payload=payload)

@router.get(
    "",
    response_model=CustomLimitOffsetPage[ReceiptRulesSchema] | list[ReceiptRulesSchema],
)
async def list_rules(
    service: Service, current_user: CurrentUser, page_filter: PageFilter
):
    return await service.list_all(page_filter=page_filter, user=current_user)

@router.post("/seed", response_model=ReceiptRulesSeedSchema, status_code=HTTPStatus.CREATED)
async def seed(
    service: Service,
    current_user: CurrentUser,
) -> ReceiptRulesSeedSchema:
    return await service.seed_defaults(user=current_user)

@router.get("/{profile_id}", response_model=ReceiptRulesSchema)
async def find_one(
    profile_id: UUID, service: Service, current_user: CurrentUser
) -> ReceiptRulesSchema:
    return await service.find_by(profile_id=profile_id, user=current_user)

@router.put("/{profile_id}", response_model=Message)
async def update(
    profile_id: UUID,
    service: Service,
    current_user: CurrentUser,
    payload: ReceiptRulesUpdateSchema,
) -> Message:
    return await service.update(
        profile_id=profile_id, payload=payload, user=current_user
    )

@router.delete("/{profile_id}", response_model=Message)
async def delete(
    profile_id: UUID, service: Service, current_user: CurrentUser
) -> Message:
    return await service.delete(profile_id=profile_id, user=current_user)