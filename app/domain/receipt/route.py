from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.receipt.service import ReceiptService
from app.domain.receipt.schema import (
    ReceiptUploadSchema,
    BatchReceiptSchema,
    ReceiptSchema, ReceiptConfirmSchema,
)
from app.models import User
from app.shared.schemas import FilterPage, Message

from app.domain.receipt.rules.route import router as receipt_rules_router
from app.domain.receipt.payment.route import router as receipt_payment_router
router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]

CurrentUser = Annotated[User, Depends(get_current_user)]


def receipt_service(session: Session) -> ReceiptService:
    return ReceiptService.from_session(session)


def receipt_filter(
    page: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1)] = 12,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FilterPage:
    return FilterPage.build(page=page, limit=limit, offset=offset)


Service = Annotated[ReceiptService, Depends(receipt_service)]

router.include_router(receipt_rules_router, prefix="/rules", tags=["Receipt Rules"])
router.include_router(receipt_payment_router, prefix="/payments", tags=["Receipt Payment"])

@router.post("/upload", response_model=ReceiptUploadSchema)
async def upload_receipt(
    service: Service,
    current_user: CurrentUser,
    file: UploadFile = File(...),
):
    return await service.upload(file=file, user=current_user)


@router.post("/batch", response_model=BatchReceiptSchema)
async def upload_batch(
    service: Service,
    current_user: CurrentUser,
    files: Annotated[list[UploadFile], File(...)],
):
    return await service.batch(files=files, user=current_user)


@router.get(
    "",
    response_model=CustomLimitOffsetPage[ReceiptSchema] | list[ReceiptSchema],
    status_code=HTTPStatus.OK,
)
async def list_all(
    service: Service,
    current_user: CurrentUser,
    page_filter: Annotated[FilterPage, Depends(receipt_filter)],
):
    return await service.list_all(page_filter=page_filter, user=current_user)


@router.get("/{receipt_id}", response_model=ReceiptSchema, status_code=HTTPStatus.OK)
async def find_one(receipt_id: UUID, service: Service, current_user: CurrentUser):
    return await service.find_one(receipt_id=receipt_id, user=current_user)

@router.post("/{receipt_id}/confirm", response_model=Message, status_code=HTTPStatus.OK)
async def confirm_receipt(receipt_id: UUID, service: Service, current_user: CurrentUser, payload: ReceiptConfirmSchema):
    return await service.confirm(receipt_id=receipt_id, user=current_user, payload=payload)
