from __future__ import annotations

import logging
from http import HTTPStatus
from uuid import UUID

from fastapi import HTTPException

from app.core.logging import LoggingParams
from app.domain.institution.repository import InstitutionRepository
from app.domain.institution.schema import (
    InstitutionCreateSchema,
    InstitutionSchema,
    InstitutionUpdateSchema,
)
from app.models import Institution, User
from app.shared.utils.string import to_snake_case
from app.temp import BaseService

logger = logging.getLogger(__name__)


class InstitutionService(
    BaseService[
        Institution, InstitutionCreateSchema, InstitutionUpdateSchema, InstitutionSchema
    ]
):
    repository_class = InstitutionRepository

    def __init__(self, repository: InstitutionRepository) -> None:
        super().__init__(
            repository,
            alias="Institution",
            logger_params=LoggingParams(
                logger=logger, service="InstitutionService", operation="institution"
            ),
            schema_class=InstitutionSchema,
            cache_prefix="institution",
        )

    def _build_entity(self, user_id: UUID, data: dict[str, object]) -> Institution:
        name = data.get("name")
        name_code = data.get("name_code")
        if not isinstance(name, str) or not isinstance(name_code, str):
            raise ValueError(
                "Institution requires normalized name and name_code strings"
            )
        return Institution(user_id=user_id, name=name, name_code=name_code)

    async def _normalize(
        self, data: dict[str, object], user: User, entity_id: UUID | None = None
    ) -> dict[str, object]:
        if "name" in data:
            name = data["name"]
            if not isinstance(name, str):
                raise ValueError("Institution name must be a string")
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
                    status_code=HTTPStatus.CONFLICT,
                    detail="Institution already exists",
                )
        return data

    async def resolve(self, user: User, name: str) -> Institution:
        async with self._operation("resolve", user.username):
            payload = InstitutionCreateSchema(name=name)
            entity = await self._find(
                user_id=user.id,
                filters={"name_code": to_snake_case(payload.name)},
                required=False,
            )
            return entity if entity is not None else await self._create(user, payload)
