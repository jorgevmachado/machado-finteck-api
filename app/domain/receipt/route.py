from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import get_current_user
from app.domain.receipt.service import ReceiptService
from app.domain.receipt.schema import ReceiptUploadSchema
from app.models import User

from app.domain.receipt.rules.route import router as receipt_rules_router

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]

CurrentUser = Annotated[User, Depends(get_current_user)]


def receipt_service(session: Session) -> ReceiptService:
    return ReceiptService.from_session(session)


Service = Annotated[ReceiptService, Depends(receipt_service)]

router.include_router(receipt_rules_router, prefix="/rules", tags=["Receipt Rules"])


@router.post("/upload", response_model=ReceiptUploadSchema)
async def upload_receipt(
    service: Service,
    current_user: CurrentUser,
    file: UploadFile = File(...),
):
    return await service.upload_receipt(file=file, user=current_user)
