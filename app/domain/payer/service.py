from __future__ import annotations

import logging
from http import HTTPStatus
from uuid import UUID

from fastapi import HTTPException

from app.core.logging import LoggingParams
from app.domain.payer.repository import PayerRepository
from app.domain.payer.schema import PayerCreateSchema, PayerSchema, PayerUpdateSchema
from app.models import Payer, User
from app.shared.utils.string import to_snake_case
from app.temp import BaseService

logger = logging.getLogger(__name__)


class PayerService(
    BaseService[Payer, PayerCreateSchema, PayerUpdateSchema, PayerSchema]
):
    repository_class = PayerRepository

    def __init__(self, repository: PayerRepository) -> None:
        super().__init__(
            repository,
            alias="Payer",
            logger_params=LoggingParams(
                logger=logger, service="PayerService", operation="payer"
            ),
            schema_class=PayerSchema,
            cache_prefix="payer",
        )

    def _build_entity(self, user_id: UUID, data: dict[str, object]) -> Payer:
        name = data.get("name")
        name_code = data.get("name_code")
        if not isinstance(name, str) or not isinstance(name_code, str):
            raise ValueError("Payer requires normalized name and name_code strings")
        return Payer(user_id=user_id, name=name, name_code=name_code)

    async def _normalize(
        self, data: dict[str, object], user: User, entity_id: UUID | None = None
    ) -> dict[str, object]:
        if "name" in data:
            name = data["name"]
            if not isinstance(name, str):
                raise ValueError("Payer name must be a string")
            data["name_code"] = to_snake_case(name)
            duplicate = await self._find(
                user_id=user.id,
                filters={"name_code": data["name_code"]},
                required=False,
            )
            if duplicate is not None and (
                entity_id is None or duplicate.id != entity_id
            ):
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT, detail="Payer already exists"
                )
        return data

    async def resolve(self, user: User, name: str) -> Payer:
        async with self._operation("resolve", user.username):
            payload = PayerCreateSchema(name=name)
            entity = await self._find(
                user_id=user.id,
                filters={"name_code": to_snake_case(payload.name)},
                required=False,
            )
            return entity if entity is not None else await self._create(user, payload)
