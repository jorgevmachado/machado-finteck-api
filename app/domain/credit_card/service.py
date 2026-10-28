from __future__ import annotations

import logging
from http import HTTPStatus
from uuid import UUID

from fastapi import HTTPException

from app.core.logging import LoggingParams
from app.domain.credit_card.repository import CreditCardRepository
from app.domain.credit_card.schema import (
    CreditCardSchema,
    CreditCardCreateSchema,
    CreditCardUpdateSchema,
)
from app.models import CreditCard, CreditCardBrandEnum, User
from app.temp import BaseService

logger = logging.getLogger(__name__)


class CreditCardService(
    BaseService[
        CreditCard, CreditCardCreateSchema, CreditCardUpdateSchema, CreditCardSchema
    ]
):
    repository_class = CreditCardRepository
    repository: CreditCardRepository

    def __init__(self, repository: CreditCardRepository) -> None:
        super().__init__(
            repository,
            alias="CreditCard",
            logger_params=LoggingParams(
                logger=logger, service="CreditCardService", operation="CreditCard"
            ),
            schema_class=CreditCardSchema,
            cache_prefix="credit_card",
        )

    def _build_entity(self, user_id: UUID, data: dict[str, object]) -> CreditCard:
        name = data.get("name")
        brand = data.get("brand")
        closing_day = data.get("closing_day")
        due_day = data.get("due_day")
        is_active = data.get("is_active")
        if not isinstance(name, str) or not isinstance(brand, CreditCardBrandEnum):
            raise ValueError("CreditCard requires a name and brand")
        if not isinstance(closing_day, int) or not isinstance(due_day, int):
            raise ValueError("CreditCard requires closing_day and due_day")
        if not isinstance(is_active, bool):
            raise ValueError("CreditCard requires is_active")
        icon = data.get("icon")
        color = data.get("color")
        description = data.get("description")
        last_four_digits = data.get("last_four_digits")
        limit = data.get("limit")
        return CreditCard(
            user_id=user_id,
            name=name,
            icon=icon if isinstance(icon, str) else None,
            brand=brand,
            color=color if isinstance(color, str) else None,
            is_active=is_active,
            description=description if isinstance(description, str) else None,
            last_four_digits=(
                last_four_digits if isinstance(last_four_digits, str) else None
            ),
            closing_day=closing_day,
            due_day=due_day,
            limit=limit if isinstance(limit, int) else None,
        )

    async def _normalize(
        self, data: dict[str, object], user: User, entity_id: UUID | None = None
    ) -> dict[str, object]:
        if "name" in data:
            name = data["name"]
            if not isinstance(name, str):
                raise ValueError("CreditCard name must be a string")
            duplicate = await self.repository.find_by_name(user_id=user.id, name=name)
            if duplicate is not None and (
                entity_id is None or duplicate.id != entity_id
            ):
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT,
                    detail="CreditCard already exists",
                )
        return data
