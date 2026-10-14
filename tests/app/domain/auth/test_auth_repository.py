from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.auth.repository import AuthRepository
from app.domain.auth.schema import RegisterSchema
from app.models.auth.enums import StatusEnum


def build_register_schema() -> RegisterSchema:
    return RegisterSchema(
        name="Ash Ketchum",
        email="ash@example.com",
        username="ash",
        date_of_birth=datetime(1990, 1, 1, tzinfo=timezone.utc),
        password="StrongPass123",
    )


class TestAuthRepository:
    @staticmethod
    @pytest.mark.asyncio
    async def test_initialize_role_returns_existing_role():
        session = AsyncMock()
        repository = AuthRepository(session=session)
        expected = SimpleNamespace(id=uuid4(), name="USER")
        session.scalar.return_value = expected

        result = await repository.initialize_role("USER")

        assert result is expected
        session.scalar.assert_awaited_once()
        session.add.assert_not_called()

    @staticmethod
    @pytest.mark.asyncio
    async def test_initialize_role_creates_missing_role():
        session = AsyncMock()
        repository = AuthRepository(session=session)
        session.scalar.return_value = None

        result = await repository.initialize_role("USER")

        assert result.name == "USER"
        session.add.assert_called_once_with(result)
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(result)

    @staticmethod
    @pytest.mark.asyncio
    async def test_initialize_role_raises_for_unknown_name():
        session = AsyncMock()
        repository = AuthRepository(session=session)
        session.scalar.return_value = None

        with pytest.raises(ValueError, match="NINJA not found"):
            await repository.initialize_role("NINJA")

    @staticmethod
    @pytest.mark.asyncio
    async def test_getters_delegate_to_session_scalar():
        session = AsyncMock()
        repository = AuthRepository(session=session)

        await repository.get_user_by_email("ash@example.com")
        await repository.get_user_by_username("ash")
        await repository.get_user_by_email_or_username("ash")

        assert session.scalar.await_count == 3

    @staticmethod
    @pytest.mark.asyncio
    async def test_convert_password_adds_and_refreshes_password():
        session = AsyncMock()
        repository = AuthRepository(session=session)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.domain.auth.repository.get_password_hash", lambda value: f"hash:{value}")
            await repository.convert_password(uuid4(), "secret")

        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_initialize_authentication_adds_and_refreshes_authentication():
        session = AsyncMock()
        repository = AuthRepository(session=session)

        await repository.initialize_authentication(uuid4())

        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_create_user_adds_and_refreshes_user():
        session = AsyncMock()
        repository = AuthRepository(session=session)
        created = SimpleNamespace(id=uuid4())
        session.refresh.side_effect = lambda user: setattr(user, "id", created.id)

        result = await repository.create_user(
            role_id=uuid4(),
            email="ash@example.com",
            name="Ash",
            username="ash",
            date_of_birth=datetime(1990, 1, 1, tzinfo=timezone.utc),
        )

        assert result.id == created.id
        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_validate_password_checks_latest_password():
        session = AsyncMock()
        repository = AuthRepository(session=session)
        session.scalar.return_value = SimpleNamespace(value="hashed")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "app.domain.auth.repository.verify_password",
                lambda raw, hashed: raw == hashed,
            )
            result = await repository.validate_password(uuid4(), "hashed")

        assert result is True
        session.scalar.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_validate_password_returns_false_when_user_has_no_password():
        session = AsyncMock()
        repository = AuthRepository(session=session)
        session.scalar.return_value = None

        result = await repository.validate_password(uuid4(), "secret")

        assert result is False

    @staticmethod
    @pytest.mark.asyncio
    async def test_update_status_executes_update_and_commits():
        session = AsyncMock()
        repository = AuthRepository(session=session)

        await repository.update_status(uuid4(), StatusEnum.ACTIVE)

        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_persist_authentication_creates_missing_authentication_and_returns_info():
        session = AsyncMock()
        repository = AuthRepository(session=session)
        session.scalar.return_value = None
        authentication = SimpleNamespace(
            total=0,
            total_success=0,
            total_failures=0,
            failed_attempts=0,
            last_authentication_at=None,
        )
        repository.initialize_authentication = AsyncMock(return_value=authentication)

        result = await repository.persist_authentication(uuid4(), is_valid=True)

        assert result.total == 1
        assert result.total_success == 1
        assert result.total_failures == 0
        assert result.failed_attempts == 0
        repository.initialize_authentication.assert_awaited_once()

    @staticmethod
    @pytest.mark.asyncio
    async def test_persist_authentication_locks_account_when_failures_reach_three():
        session = AsyncMock()
        repository = AuthRepository(session=session)
        authentication = SimpleNamespace(
            total=2,
            total_success=1,
            total_failures=2,
            failed_attempts=2,
            last_authentication_at=None,
        )
        session.scalar.return_value = authentication
        repository.update_status = AsyncMock()

        result = await repository.persist_authentication(uuid4(), is_valid=False)

        assert result is None
        assert session.commit.await_count == 1
        session.refresh.assert_awaited_once_with(authentication)
        repository.update_status.assert_awaited_once()
