from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.transaction.statement.schema import (
    StatementFilterSchema,
    StatementEntrySchema,
)
from app.domain.transaction.statement.service import StatementService
from app.models import User

router = APIRouter()


def statement_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StatementService:
    return StatementService.from_session(session)


@router.get(
    "",
    response_model=CustomLimitOffsetPage[StatementEntrySchema]
    | list[StatementEntrySchema],
    status_code=HTTPStatus.OK,
)
async def list_statement(
    service: Annotated[StatementService, Depends(statement_service)],
    current_user: Annotated[User, Depends(get_current_user)],
    page_filter: Annotated[StatementFilterSchema, Query()],
) -> list[StatementEntrySchema] | CustomLimitOffsetPage[StatementEntrySchema]:
    return await service.list_all(user=current_user, page_filter=page_filter)
