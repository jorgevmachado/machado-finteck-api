from http import HTTPStatus
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from jwt import decode

from app.core.security import create_access_token, get_current_user
from app.core.settings import Settings


def test_jwt():
    data = {"test": "test"}

    token = create_access_token(data)

    decoded = decode(token, Settings().SECRET_KEY, algorithms=Settings().ALGORITHM)

    assert decoded["test"] == "test"
    assert "exp" in decoded


@pytest.mark.asyncio
async def test_jwt_invalid_token():
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(session=AsyncMock(), token="invalid")

    assert exc_info.value.status_code == HTTPStatus.UNAUTHORIZED
    assert exc_info.value.detail == "Could not validate credentials"


@pytest.mark.asyncio
async def test_get_current_user_not_found():
    data = {"no-email": "no-email"}
    token = create_access_token(data)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(session=AsyncMock(), token=token)

    assert exc_info.value.status_code == HTTPStatus.UNAUTHORIZED
    assert exc_info.value.detail == "Could not validate credentials"


@pytest.mark.asyncio
async def test_get_current_user_does_not_exists():
    data = {"sub": str(uuid4())}
    token = create_access_token(data)
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(session=session, token=token)

    assert exc_info.value.status_code == HTTPStatus.UNAUTHORIZED
    assert exc_info.value.detail == "Could not validate credentials"
