from __future__ import annotations

import logging
from http import HTTPStatus

from fastapi import HTTPException

from app.core.exceptions import handle_service_exception
from app.core.security import create_access_token
from app.domain.auth.repository import AuthRepository
from app.domain.auth.schema import (
    LoginResponseSchema,
    LoginSchema,
    RegisterSchema,
    AuthSchema,
)

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, repository: AuthRepository) -> None:
        self.repository = repository

    async def validate_user(self, email: str, username: str):
        existing_email = await self.repository.get_user_by_email(email)
        if existing_email:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail="Email already registered",
            )

        existing_username = await self.repository.get_user_by_username(username)
        if existing_username:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT,
                detail="Username already taken",
            )

    async def register(self, data: RegisterSchema) -> AuthSchema:
        try:
            role = await self.repository.initialize_role()
            await self.validate_user(data.email, data.username)
            user = await self.repository.create_user(
                name=data.name,
                email=data.email,
                role_id=role.id,
                username=data.username,
                date_of_birth=data.date_of_birth,
            )

            await self.repository.convert_password(user.id, data.password)
            await self.repository.initialize_authentication(user.id)

            return AuthSchema(
                id=user.id,
                role=role.name,
                name=user.name,
                email=user.email,
                username=user.username,
                status=user.status,
                created_at=user.created_at,
            )

        except Exception as exception:
            handle_service_exception(
                exception,
                logger=logger,
                service="AuthService",
                operation="register",
                raise_exception=True,
            )

    async def login(self, data: LoginSchema) -> LoginResponseSchema:
        try:
            user = await self.repository.get_user_by_email_or_username(data.credential)
            if not user:
                raise HTTPException(
                    status_code=HTTPStatus.UNAUTHORIZED,
                    detail="Invalid credentials",
                )

            is_valid = await self.repository.validate_password(
                user_id=user.id, password=data.password
            )
            info = await self.repository.persist_authentication(
                user_id=user.id, is_valid=is_valid
            )

            if not info:
                raise HTTPException(
                    status_code=HTTPStatus.UNAUTHORIZED,
                    detail="Account locked due to multiple failed login attempts",
                )

            if not is_valid:
                raise HTTPException(
                    status_code=HTTPStatus.UNAUTHORIZED,
                    detail="Invalid credentials",
                )

            token = create_access_token({"sub": str(user.id), "role": user.role.name})

            return LoginResponseSchema(access_token=token)

        except Exception as exception:
            handle_service_exception(
                exception,
                logger=logger,
                service="AuthService",
                operation="login",
                raise_exception=True,
            )
