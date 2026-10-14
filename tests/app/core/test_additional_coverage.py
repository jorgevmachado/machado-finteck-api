from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi_pagination import LimitOffsetParams
from pydantic import BaseModel

from app.core.cache.service import CacheService
from app.core.exceptions.exceptions import _resolve_status_code
from app.core.logging import LoggingParams
from app.core.pagination.schemas import CustomLimitOffsetPage
from app.core.security import get_current_user, get_password_hash, verify_password
from app.core.service.base import BaseService


class DummySchema(BaseModel):
    id: int
    name: str


class DummyUpdateSchema(BaseModel):
    name: str


def build_cache_service() -> CacheService:
    return CacheService(
        alias="dummy",
        prefix="dummy",
        logger_params=LoggingParams(
            logger=__import__("logging").getLogger(__name__),
            service="DummyService",
            operation="dummy",
        ),
        schema_class=DummySchema,
    )


class TestCacheServiceAdditionalCoverage:
    @staticmethod
    @pytest.mark.asyncio
    async def test_get_list_supports_custom_paginate_payload():
        service = build_cache_service()
        payload = (
            CustomLimitOffsetPage[DummySchema]
            .create(
                items=[{"id": 1, "name": "pikachu"}],
                total=1,
                params=LimitOffsetParams(limit=10, offset=0),
            )
            .model_dump(mode="json")
        )
        service.cache.get_cache = AsyncMock(
            return_value={"type": "custom-paginate", "data": payload}
        )

        result = await service.get_list("dummy:list")

        assert result.meta.total == 1
        assert result.items[0].name == "pikachu"

    @staticmethod
    @pytest.mark.asyncio
    async def test_set_list_supports_custom_paginate_payload():
        service = build_cache_service()
        service.cache.set_cache = AsyncMock()
        page = CustomLimitOffsetPage[DummySchema].create(
            items=[{"id": 1, "name": "pikachu"}],
            total=1,
            params=LimitOffsetParams(limit=10, offset=0),
        )

        await service.set_list("dummy:list", page)

        service.cache.set_cache.assert_awaited_once()
        assert service.cache.set_cache.await_args.args[1]["type"] == "custom-paginate"


class DummyRepository:
    async def find_by(self, **kwargs):
        return {"id": "1", "name": "old-name"}

    async def update(self, entity):
        return entity


class TestSecurityAndServiceAdditionalCoverage:
    @staticmethod
    def test_password_hash_and_verify_roundtrip():
        hashed = get_password_hash("pikachu123")
        assert verify_password("pikachu123", hashed) is True

    @staticmethod
    @pytest.mark.asyncio
    async def test_get_current_user_returns_user():
        user = SimpleNamespace(id="user-id")
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=user)
        token = __import__(
            "app.core.security.security", fromlist=["create_access_token"]
        ).create_access_token({"sub": "5d01756e-7ca5-4c79-969d-fdbd2d289f8b"})

        result = await get_current_user(session=session, token=token)

        assert result is user

    @staticmethod
    def test_resolve_status_code_handles_httpx_errors():
        assert _resolve_status_code(httpx.HTTPError("boom")).value == 503

    @staticmethod
    @pytest.mark.asyncio
    async def test_base_service_update_supports_dict_entities():
        service = BaseService(
            alias="dummy",
            repository=DummyRepository(),
            logger_params=LoggingParams(
                logger=__import__("logging").getLogger(__name__),
                service="DummyService",
                operation="dummy",
            ),
            schema_class=DummySchema,
        )

        updated = await service.update("1", DummyUpdateSchema(name="new-name"))

        assert updated["name"] == "new-name"
