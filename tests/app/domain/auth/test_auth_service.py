from __future__ import annotations

from datetime import datetime, timezone
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.domain.auth.schema import LoginSchema, RegisterSchema
from app.domain.auth.service import AuthService
from app.models.auth.enums import StatusEnum


def build_register_schema() -> RegisterSchema:
    return RegisterSchema(
        name="Ash Ketchum",
        email="ash@example.com",
        username="ash",
        date_of_birth=datetime(1990, 1, 1, tzinfo=timezone.utc),
        password="StrongPass123",
    )


class TestAuthSchema:
    @staticmethod
    def test_register_schema_rejects_short_password():
        with pytest.raises(ValidationError):
            RegisterSchema(
                name="Ash",
                email="ash@example.com",
                username="ash",
                date_of_birth=datetime(1990, 1, 1, tzinfo=timezone.utc),
                password="short",
            )


class TestAuthService:
    @staticmethod
    @pytest.mark.asyncio
    async def test_validate_user_rejects_existing_email():
        repository = AsyncMock()
        repository.get_user_by_email.return_value = object()
        service = AuthService(repository=repository)

        with pytest.raises(HTTPException) as exc:
            await service.validate_user("ash@example.com", "ash")

        assert exc.value.status_code == HTTPStatus.CONFLICT
        assert exc.value.detail == "Email already registered"

    @staticmethod
    @pytest.mark.asyncio
    async def test_validate_user_rejects_existing_username():
        repository = AsyncMock()
        repository.get_user_by_email.return_value = None
        repository.get_user_by_username.return_value = object()
        service = AuthService(repository=repository)

        with pytest.raises(HTTPException) as exc:
            await service.validate_user("ash@example.com", "ash")

        assert exc.value.status_code == HTTPStatus.CONFLICT
        assert exc.value.detail == "Username already taken"

    @staticmethod
    @pytest.mark.asyncio
    async def test_register_returns_auth_schema():
        repository = AsyncMock()
        repository.initialize_role.return_value = SimpleNamespace(
            id=uuid4(),
            name="USER",
        )
        repository.get_user_by_email.return_value = None
        repository.get_user_by_username.return_value = None
        created_user = SimpleNamespace(
            id=uuid4(),
            name="Ash Ketchum",
            email="ash@example.com",
            username="ash",
            status=StatusEnum.ACTIVE,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        repository.create_user.return_value = created_user

        service = AuthService(repository=repository)
        result = await service.register(build_register_schema())

        assert result.id == created_user.id
        assert result.role == "USER"
        assert result.email == created_user.email
        assert result.username == created_user.username
        repository.convert_password.assert_awaited_once_with(
            created_user.id, "StrongPass123"
        )
        repository.initialize_authentication.assert_awaited_once_with(created_user.id)

    @staticmethod
    @pytest.mark.asyncio
    async def test_register_handles_repository_exception():
        repository = AsyncMock()
        repository.initialize_role.side_effect = RuntimeError("boom")
        service = AuthService(repository=repository)

        with patch("app.domain.auth.service.handle_service_exception") as mock_handle:
            result = await service.register(build_register_schema())

        assert result is None
        mock_handle.assert_called_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_login_rejects_missing_user():
        repository = AsyncMock()
        repository.get_user_by_email_or_username.return_value = None
        service = AuthService(repository=repository)

        with pytest.raises(HTTPException) as exc:
            await service.login(LoginSchema(credential="ash", password="StrongPass123"))

        assert exc.value.status_code == HTTPStatus.UNAUTHORIZED
        assert exc.value.detail == "Invalid credentials"

    @staticmethod
    @pytest.mark.asyncio
    async def test_login_rejects_locked_account_when_auth_info_missing():
        user = SimpleNamespace(id=uuid4(), role=SimpleNamespace(name="USER"))
        repository = AsyncMock()
        repository.get_user_by_email_or_username.return_value = user
        repository.validate_password.return_value = True
        repository.persist_authentication.return_value = None
        service = AuthService(repository=repository)

        with pytest.raises(HTTPException) as exc:
            await service.login(LoginSchema(credential="ash", password="StrongPass123"))

        assert exc.value.status_code == HTTPStatus.UNAUTHORIZED
        assert exc.value.detail == "Account locked due to multiple failed login attempts"

    @staticmethod
    @pytest.mark.asyncio
    async def test_login_rejects_invalid_password():
        user = SimpleNamespace(id=uuid4(), role=SimpleNamespace(name="USER"))
        repository = AsyncMock()
        repository.get_user_by_email_or_username.return_value = user
        repository.validate_password.return_value = False
        repository.persist_authentication.return_value = SimpleNamespace(
            total=1,
            total_success=0,
            total_failures=1,
            last_authentication_at=datetime.now(timezone.utc),
        )
        service = AuthService(repository=repository)

        with pytest.raises(HTTPException) as exc:
            await service.login(LoginSchema(credential="ash", password="WrongPass"))

        assert exc.value.status_code == HTTPStatus.UNAUTHORIZED
        assert exc.value.detail == "Invalid credentials"

    @staticmethod
    @pytest.mark.asyncio
    async def test_login_returns_access_token_for_valid_user(monkeypatch):
        user = SimpleNamespace(
            id=uuid4(),
            role=SimpleNamespace(name="USER"),
        )
        repository = AsyncMock()
        repository.get_user_by_email_or_username.return_value = user
        repository.validate_password.return_value = True
        repository.persist_authentication.return_value = SimpleNamespace(
            total=1,
            total_success=1,
            total_failures=0,
            last_authentication_at=datetime.now(timezone.utc),
        )
        monkeypatch.setattr(
            "app.domain.auth.service.create_access_token",
            lambda payload: f"token-{payload['sub']}",
        )

        service = AuthService(repository=repository)
        result = await service.login(
            LoginSchema(credential="ash", password="StrongPass123")
        )

        assert result.access_token == f"token-{user.id}"
        assert result.token_type == "bearer"
        repository.persist_authentication.assert_awaited_once_with(
            user_id=user.id, is_valid=True
        )
