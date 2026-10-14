from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.auth.route import get_auth_service, login, me, register
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


class TestAuthRoutes:
    @staticmethod
    def test_get_auth_service_builds_service():
        service = get_auth_service(AsyncMock())
        assert isinstance(service, AuthService)

    @staticmethod
    @pytest.mark.asyncio
    async def test_register_route_returns_service_result():
        service = AsyncMock()
        data = build_register_schema()
        expected = SimpleNamespace(id=uuid4())
        service.register.return_value = expected

        result = await register(data, service=service)

        assert result is expected

    @staticmethod
    @pytest.mark.asyncio
    async def test_login_route_returns_token_payload():
        service = AsyncMock()
        service.login.return_value = SimpleNamespace(
            access_token="token",
            token_type="bearer",
        )

        result = await login(
            LoginSchema(credential="ash", password="StrongPass123"),
            service=service,
        )

        assert result.access_token == "token"
        service.login.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_me_route_builds_auth_schema_from_current_user():
        now = datetime.now(timezone.utc)
        current_user = SimpleNamespace(
            id=uuid4(),
            role=SimpleNamespace(name="USER"),
            name="Ash",
            email="ash@example.com",
            username="ash",
            status=StatusEnum.ACTIVE,
            authentication=SimpleNamespace(
                total=2,
                total_success=1,
                total_failures=1,
                failed_attempts=1,
                last_authentication_at=now,
            ),
            created_at=now,
            updated_at=None,
            deleted_at=None,
        )

        result = await me(current_user)

        assert result.id == current_user.id
        assert result.role == "USER"
        assert result.email == current_user.email
        assert result.username == current_user.username
        assert result.info.total == 2
        assert result.info.total_success == 1
        assert result.info.total_failures == 1
        assert result.info.failed_attempts == 1
