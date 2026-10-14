from __future__ import annotations

from datetime import datetime
from typing import Annotated
from fastapi import Depends
from uuid import UUID

from sqlalchemy import or_, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import get_password_hash, verify_password
from app.domain.auth.schema import AuthInfoSchema
from app.models import Role, User, StatusEnum, Password, Authentication, utcnow
from app.shared.utils.string import to_snake_case

Session = Annotated[AsyncSession, Depends(get_session)]


class AuthRepository:
    def __init__(self, session: Session):
        self.session = session

    async def initialize_role(self, name: str = "USER") -> Role:
        name_code = to_snake_case(name)
        role = await self.session.scalar(select(Role).filter_by(name_code=name_code))
        if not role:
            if name_code != "user" and name_code != "admin":
                raise ValueError(f"{name} not found")
            role = Role(name=name, name_code=name_code, description=f"{name} role")
            self.session.add(role)
            await self.session.commit()
            await self.session.refresh(role)
        return role

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.session.scalar(select(User).where(User.email == email))
        return result

    async def get_user_by_email_or_username(self, credential: str) -> User | None:
        result = await self.session.scalar(
            select(User).where(
                or_(User.email == credential, User.username == credential)
            )
        )
        return result

    async def create_user(
        self,
        role_id: UUID,
        email: str,
        name: str,
        username: str,
        date_of_birth: datetime,
    ) -> User:
        user = User(
            name=name,
            email=email,
            status=StatusEnum.ACTIVE,
            role_id=role_id,
            username=username,
            date_of_birth=date_of_birth,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def convert_password(self, user_id: UUID, password: str) -> None:
        value = get_password_hash(password)
        password = Password(value=value, user_id=user_id, last_value=value)
        self.session.add(password)
        await self.session.commit()
        await self.session.refresh(password)
        return None

    async def initialize_authentication(self, user_id: UUID) -> None:
        authentication = Authentication(user_id=user_id)
        self.session.add(authentication)
        await self.session.commit()
        await self.session.refresh(authentication)

    async def get_user_by_username(self, username: str) -> User | None:
        result = await self.session.scalar(
            select(User).where(User.username == username)
        )
        return result

    async def validate_password(self, user_id: UUID, password: str) -> bool:
        current_password = await self.session.scalar(
            select(Password)
            .where(Password.user_id == user_id)
            .order_by(Password.created_at.desc())
        )
        if not current_password:
            return False
        return verify_password(password, current_password.value)

    async def update_status(self, user_id: UUID, status: StatusEnum) -> None:
        now = utcnow()
        await self.session.execute(
            sa_update(User)
            .where(User.id == user_id)
            .values(status=status, updated_at=now)
        )
        await self.session.commit()

    async def persist_authentication(
        self, user_id: UUID, is_valid: bool, threshold: int = 3
    ) -> AuthInfoSchema | None:
        authentication = await self.session.scalar(
            select(Authentication).where(Authentication.user_id == user_id)
        )
        if not authentication:
            authentication = await self.initialize_authentication(user_id=user_id)

        authentication.total = authentication.total + 1
        authentication.total_failures = authentication.total_failures + (
            0 if is_valid else 1
        )
        authentication.failed_attempts = (
            0 if is_valid else authentication.failed_attempts + 1
        )
        authentication.total_success = authentication.total_success + (
            1 if is_valid else 0
        )
        authentication.last_authentication_at = (
            utcnow() if is_valid else authentication.last_authentication_at
        )

        self.session.add(authentication)
        await self.session.commit()
        await self.session.refresh(authentication)

        if authentication.failed_attempts >= threshold:
            await self.update_status(user_id=user_id, status=StatusEnum.LOCKED)
            return None

        return AuthInfoSchema(
            total=authentication.total,
            total_success=authentication.total_success,
            total_failures=authentication.total_failures,
            failed_attempts=authentication.failed_attempts,
            last_authentication_at=authentication.last_authentication_at,
        )
