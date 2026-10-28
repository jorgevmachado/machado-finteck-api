from __future__ import annotations

import logging
from http import HTTPStatus
from uuid import UUID

from fastapi import HTTPException

from app.core.logging import LoggingParams
from app.domain.beneficiary.repository import BeneficiaryRepository
from app.domain.beneficiary.schema import (
    BeneficiaryCreateSchema,
    BeneficiarySchema,
    BeneficiaryUpdateSchema,
)
from app.models import Beneficiary, User
from app.shared.utils.string import to_snake_case
from app.temp import BaseService

logger = logging.getLogger(__name__)


class BeneficiaryService(
    BaseService[
        Beneficiary, BeneficiaryCreateSchema, BeneficiaryUpdateSchema, BeneficiarySchema
    ]
):
    repository_class = BeneficiaryRepository

    def __init__(self, repository: BeneficiaryRepository) -> None:
        super().__init__(
            repository,
            alias="Beneficiary",
            logger_params=LoggingParams(
                logger=logger, service="BeneficiaryService", operation="beneficiary"
            ),
            schema_class=BeneficiarySchema,
            cache_prefix="beneficiary",
        )

    def _build_entity(self, user_id: UUID, data: dict[str, object]) -> Beneficiary:
        name = data.get("name")
        name_code = data.get("name_code")
        if not isinstance(name, str) or not isinstance(name_code, str):
            raise ValueError(
                "Beneficiary requires normalized name and name_code strings"
            )
        return Beneficiary(user_id=user_id, name=name, name_code=name_code)

    async def _normalize(
        self, data: dict[str, object], user: User, entity_id: UUID | None = None
    ) -> dict[str, object]:
        if "name" in data:
            name = data["name"]
            if not isinstance(name, str):
                raise ValueError("Beneficiary name must be a string")
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
                    detail="Beneficiary already exists",
                )
        return data

    async def resolve(self, user: User, name: str) -> Beneficiary:
        async with self._operation("resolve", user.username):
            payload = BeneficiaryCreateSchema(name=name)
            entity = await self._find(
                user_id=user.id,
                filters={"name_code": to_snake_case(payload.name)},
                required=False,
            )
            return entity if entity is not None else await self._create(user, payload)
