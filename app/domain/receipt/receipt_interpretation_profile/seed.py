from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.settings import Settings
from app.domain.receipt.data.schema import ReceiptData
from app.domain.receipt.receipt_interpretation_profile.business import (
    build_reconciliation_plan,
)
from app.domain.receipt.receipt_interpretation_profile.repository import (
    ReceiptInterpretationProfileRepository,
)
from app.domain.receipt.receipt_interpretation_profile.schema import (
    ProfileName,
    ReceiptFieldRuleCreateSchema,
    ReceiptFieldRuleReconcileSchema,
    ReceiptIdentificationRuleCreateSchema,
    ReceiptIdentificationRuleReconcileSchema,
    ReceiptInterpretationProfileCreateSchema,
)
from app.models import (
    ReceiptFieldRule,
    ReceiptIdentificationRule,
    ReceiptInterpretationProfile,
    User,
)

logger = logging.getLogger(__name__)
DATA_PATH = Path(__file__).parent


class ReceiptGeneralProfileSeedSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ProfileName
    institution_code: None
    is_active: StrictBool = True
    identification_rules: list[ReceiptIdentificationRuleCreateSchema] = Field(
        default_factory=list, max_length=0
    )
    field_rules: list[ReceiptFieldRuleCreateSchema] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_general(self) -> ReceiptGeneralProfileSeedSchema:
        fields = [rule.field_name for rule in self.field_rules]
        if len(set(fields)) != len(fields) or set(fields) != set(
            ReceiptData.model_fields
        ):
            raise ValueError("General seed must define each ReceiptData field once")
        if not self.is_active:
            raise ValueError("General seed must be active")
        return self


def load_seed_profiles() -> tuple[
    ReceiptGeneralProfileSeedSchema, list[ReceiptInterpretationProfileCreateSchema]
]:
    general = ReceiptGeneralProfileSeedSchema.model_validate_json(
        (DATA_PATH / "general_profile.json").read_text(encoding="utf-8")
    )
    raw = json.loads((DATA_PATH / "default_profiles.json").read_text(encoding="utf-8"))
    profiles = [
        ReceiptInterpretationProfileCreateSchema.model_validate(item) for item in raw
    ]
    codes = [profile.institution_code for profile in profiles]
    if len(codes) != len(set(codes)):
        raise ValueError("Seed contains duplicate institution codes")
    return general, profiles


async def seed_profiles(
    session: AsyncSession, user_id: UUID, *, replace_existing: bool = False
) -> tuple[int, int, int]:
    general, profiles = load_seed_profiles()
    repository = ReceiptInterpretationProfileRepository(session)
    created = updated = skipped = 0
    async with repository.transaction():
        # Serialize seed processes, including creation of the shared General.
        await session.execute(
            text(
                "SELECT pg_advisory_xact_lock(hashtextextended('receipt-profile-seed', 0))"
            )
        )
        user = await session.scalar(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        if user is None:
            raise ValueError("Seed owner must be an existing non-deleted user")
        for payload in (general, *profiles):
            owner = None if payload.institution_code is None else user_id
            existing = await session.scalar(
                select(ReceiptInterpretationProfile.id).where(
                    ReceiptInterpretationProfile.user_id == owner,
                    ReceiptInterpretationProfile.institution_code
                    == payload.institution_code,
                    ReceiptInterpretationProfile.deleted_at.is_(None),
                )
            )
            if existing is not None and not replace_existing:
                skipped += 1
                continue
            if existing is not None:
                entity = await repository.find_by(
                    id=existing, user_id=user_id, for_update=True
                )
                if entity is None:
                    raise RuntimeError("Seed profile disappeared during update")
                live_fields = {child.field_name: child for child in entity.field_rules}
                live_identification = {
                    child.pattern: child for child in entity.identification_rules
                }
                fields = [
                    ReceiptFieldRuleReconcileSchema.model_validate(
                        child.model_dump(mode="json")
                        | (
                            {"id": live_fields[child.field_name].id}
                            if child.field_name in live_fields
                            else {}
                        )
                    )
                    for child in payload.field_rules
                ]
                identification = [
                    ReceiptIdentificationRuleReconcileSchema.model_validate(
                        child.model_dump(mode="json")
                        | (
                            {"id": live_identification[child.pattern].id}
                            if child.pattern in live_identification
                            else {}
                        )
                    )
                    for child in payload.identification_rules
                ]
                entity.name = payload.name
                entity.is_active = payload.is_active
                await repository.save(
                    entity,
                    fields=build_reconciliation_plan(
                        fields, [child.id for child in entity.field_rules]
                    ),
                    identification=build_reconciliation_plan(
                        identification,
                        [child.id for child in entity.identification_rules],
                    ),
                )
                updated += 1
            else:
                entity = ReceiptInterpretationProfile(
                    user_id=owner,
                    name=payload.name,
                    institution_code=payload.institution_code,
                    is_active=payload.is_active,
                )
                entity.field_rules.extend(
                    ReceiptFieldRule(
                        profile_id=entity.id, **child.model_dump(mode="json")
                    )
                    for child in payload.field_rules
                )
                entity.identification_rules.extend(
                    ReceiptIdentificationRule(
                        profile_id=entity.id, **child.model_dump(mode="json")
                    )
                    for child in payload.identification_rules
                )
                await repository.save(entity)
                created += 1
    return created, updated, skipped


async def _run(user_id: UUID, replace_existing: bool) -> tuple[int, int, int]:
    engine = create_async_engine(Settings().DATABASE_URL)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            return await seed_profiles(
                session, user_id, replace_existing=replace_existing
            )
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed receipt interpretation profiles."
    )
    parser.add_argument("--user-id", type=UUID, required=True)
    parser.add_argument("--confirm-development", action="store_true")
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Replace existing General and target owner's bank rules with JSON defaults.",
    )
    args = parser.parse_args()
    if not args.confirm_development:
        parser.error(
            "Verify DATABASE_URL and pass --confirm-development before seeding"
        )
    try:
        created, updated, skipped = asyncio.run(
            _run(args.user_id, args.replace_existing)
        )
    except (ValueError, OSError, SQLAlchemyError, RuntimeError):
        logger.exception("Receipt profile seed failed; transaction rolled back")
        return 1
    print(
        f"Receipt profile seed: created={created}, updated={updated}, skipped={skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
