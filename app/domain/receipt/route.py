from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import get_current_user
from app.domain.receipt.service import ReceiptService
from app.models import User

from app.domain.receipt.receipt_interpretation_profile.route import router as receipt_interpretation_profile_router

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]


def receipt_service(session: Session) -> ReceiptService:
    return ReceiptService.from_session(session)


Service = Annotated[ReceiptService, Depends(receipt_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]


router.include_router(receipt_interpretation_profile_router, prefix="/receipt-interpretation-profiles", tags=["Receipt Interpretation Profiles"])