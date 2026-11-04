from __future__ import annotations

import logging
from http import HTTPStatus
from uuid import UUID

from fastapi import HTTPException

from app.core.logging import LoggingParams
from app.domain.account.repository import AccountRepository
from app.domain.account.schema import (
    AccountSchema,
    AccountCreateSchema,
    AccountUpdateSchema,
    AccountSeedSchema,
)
from app.domain.account.seeds import load_seeds_accounts
from app.models import Account, AccountTypeEnum, User
from app.core.service import BaseService

logger = logging.getLogger(__name__)


class AccountService(
    BaseService[Account, AccountCreateSchema, AccountUpdateSchema, AccountSchema]
):
    repository_class = AccountRepository
    repository: AccountRepository

    def __init__(self, repository: AccountRepository) -> None:
        super().__init__(
            repository,
            alias="Account",
            logger_params=LoggingParams(
                logger=logger, service="AccountService", operation="account"
            ),
            schema_class=AccountSchema,
            cache_prefix="account",
        )

    def _build_entity(self, user_id: UUID, data: dict[str, object]) -> Account:
        name = data.get("name")
        account_type = data.get("type")
        if not isinstance(name, str) or not isinstance(account_type, AccountTypeEnum):
            raise ValueError("Account requires a name and type")
        is_active = data.get("is_active")
        if not isinstance(is_active, bool):
            raise ValueError("Account requires is_active")
        icon = data.get("icon")
        color = data.get("color")
        agency = data.get("agency")
        description = data.get("description")
        account_number = data.get("account_number")
        financial_institution = data.get("financial_institution")
        return Account(
            user_id=user_id,
            name=name,
            type=account_type,
            icon=icon if isinstance(icon, str) else None,
            color=color if isinstance(color, str) else None,
            agency=agency if isinstance(agency, str) else None,
            description=description if isinstance(description, str) else None,
            account_number=account_number if isinstance(account_number, str) else None,
            financial_institution=(
                financial_institution
                if isinstance(financial_institution, str)
                else None
            ),
            is_active=is_active,
        )

    async def _normalize(
        self, data: dict[str, object], user: User, entity_id: UUID | None = None
    ) -> dict[str, object]:
        if "name" in data:
            name = data["name"]
            if not isinstance(name, str):
                raise ValueError("Account name must be a string")
            duplicate = await self.repository.find_by_name(user_id=user.id, name=name)
            if duplicate is not None and (
                entity_id is None or duplicate.id != entity_id
            ):
                raise HTTPException(
                    status_code=HTTPStatus.CONFLICT,
                    detail="Account already exists",
                )
        return data

    async def seed_defaults(self, user: User) -> AccountSeedSchema:
        async with self._operation("seed_defaults", user.username):
            payloads = load_seeds_accounts()
            created: list[Account] = []
            skipped = 0
            async with self.repository.transaction():
                for payload in payloads:
                    existing = await self.repository.find_by_name(
                        name=payload.name, user_id=user.id
                    )
                    if existing is not None:
                        skipped += 1
                        continue
                    entity = self._build_entity(user.id, payload.model_dump())
                    await self.repository.save(entity, user_id=user.id)
                    created.append(entity)
            if created:
                await self._invalidate_cache(user, created[0], "seed_defaults")
            return AccountSeedSchema(created=len(created), skipped=skipped)
