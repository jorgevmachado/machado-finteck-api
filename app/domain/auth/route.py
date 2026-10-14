from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.database import get_session
from app.core.security import get_current_user
from app.domain.auth.repository import AuthRepository
from app.domain.auth.schema import (
    LoginResponseSchema,
    LoginSchema,
    RegisterSchema,
    AuthSchema,
    AuthInfoSchema,
)
from app.domain.auth.service import AuthService
from app.models.auth.user import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]


def get_auth_service(session: Session) -> AuthService:
    return AuthService(AuthRepository(session))


@router.post("/register", response_model=AuthSchema, status_code=HTTPStatus.CREATED)
async def register(
    data: RegisterSchema,
    service: Annotated[AuthService, Depends(get_auth_service)],
):
    user = await service.register(data)
    return user


@router.post("/login", response_model=LoginResponseSchema, status_code=HTTPStatus.OK)
async def login(
    data: LoginSchema,
    service: Annotated[AuthService, Depends(get_auth_service)],
):
    return await service.login(data)


@router.get("/me", response_model=AuthSchema, status_code=HTTPStatus.OK)
async def me(current_user: Annotated[User, Depends(get_current_user)]):
    return AuthSchema(
        id=current_user.id,
        role=current_user.role.name,
        name=current_user.name,
        email=current_user.email,
        info=AuthInfoSchema(
            total=current_user.authentication.total,
            total_success=current_user.authentication.total_success,
            total_failures=current_user.authentication.total_failures,
            failed_attempts=current_user.authentication.failed_attempts,
            last_authentication_at=current_user.authentication.last_authentication_at,
        ),
        username=current_user.username,
        status=current_user.status,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
        deleted_at=current_user.deleted_at,
    )
