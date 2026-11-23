from __future__ import annotations

import logging
from http import HTTPStatus
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import update

from app.core.logging import LoggingParams
from app.domain.institution.repository import InstitutionRepository
from app.domain.institution.schema import (
    InstitutionCreateSchema,
    InstitutionSchema,
    InstitutionUpdateSchema,
    InstitutionSeedSchema,
)
from app.domain.institution.seeds import load_seeds_institutions
from app.models import Institution, ReceiptInterpretationProfile, User, utcnow
from app.shared.utils.string import to_snake_case
from app.core.service import BaseService

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
            if entity_id is not None:
                await self._resync_profile_codes(entity_id, data["name_code"])
        return data

    async def _resync_profile_codes(
        self, institution_id: UUID, name_code: str
    ) -> None:
        """Perfis guardam `institution_code` como snapshot de `name_code`."""
        code = name_code.upper()
        await self.repository.session.execute(
            update(ReceiptInterpretationProfile)
            .where(
                ReceiptInterpretationProfile.institution_id == institution_id,
                ReceiptInterpretationProfile.institution_code != code,
            )
            .values(institution_code=code, updated_at=utcnow())
        )

    async def resolve(self, user: User, name: str) -> Institution:
        async with self._operation("resolve", user.username):
            async with self.repository.transaction():
                return await self.resolve_in_transaction(user, name)

    async def resolve_in_transaction(self, user: User, name: str) -> Institution:
        """Idempotente por `name_code`. Exige transação já aberta pelo chamador.

        Usado pelo seed de regras, que precisa resolver instituições dentro da
        própria transação (aninhar transações não é suportado pelo repositório).
        """
        payload = InstitutionCreateSchema(name=name)
        name_code = to_snake_case(payload.name)
        entity = await self._find(
            user_id=user.id,
            filters={"name_code": name_code},
            required=False,
        )
        if entity is not None:
            return entity
        entity = self._build_entity(user.id, {"name": payload.name, "name_code": name_code})
        return await self.repository.save(entity, user_id=user.id)

    async def seed_defaults(self, user: User) -> InstitutionSeedSchema:
        async with self._operation("seed_defaults", user.username):
            payloads = load_seeds_institutions()
            created: list[Institution] = []
            skipped = 0
            async with self.repository.transaction():
                for payload in payloads:
                    name_code = to_snake_case(payload.name)
                    existing = await self._find(
                        user_id=user.id,
                        filters={"name_code": name_code},
                        required=False,
                    )
                    if existing is not None:
                        skipped += 1
                        continue
                    entity = self._build_entity(
                        user.id, {"name": payload.name, "name_code": name_code}
                    )
                    await self.repository.save(entity, user_id=user.id)
                    created.append(entity)
            if created:
                await self._invalidate_cache(user, created[0], "seed_defaults")
            return InstitutionSeedSchema(created=len(created), skipped=skipped)
