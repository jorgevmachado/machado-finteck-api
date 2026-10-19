from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.settings import Settings
from app.domain.category.repository import CategoryRepository
from app.domain.category.schema import CategoryCreateSchema
from app.models import Category, Subcategory, User

SEED_DATA_PATH = Path(__file__).parent / "data" / "categories.json"
SEED_USER_EMAIL = "usuario@formacao.dev"


class SeedUserNotFoundError(RuntimeError):
    pass


def load_seed_categories() -> list[CategoryCreateSchema]:
    raw_data: list[dict[str, Any]] = json.loads(
        SEED_DATA_PATH.read_text(encoding="utf-8")
    )
    return [CategoryCreateSchema.model_validate(item) for item in raw_data]


async def seed_categories(session: AsyncSession) -> tuple[int, int]:
    user = await session.scalar(select(User).where(User.email == SEED_USER_EMAIL))
    if user is None:
        raise SeedUserNotFoundError(
            f"Required development user {SEED_USER_EMAIL} does not exist"
        )

    repository = CategoryRepository(session)
    created = 0
    ignored = 0
    async with repository.transaction():
        for payload in load_seed_categories():
            existing = await repository.find_by_name(
                name=payload.name,
                user_id=user.id,
            )
            if existing is not None:
                ignored += 1
                continue

            category = Category(
                user_id=user.id,
                name=payload.name,
                icon=payload.icon,
                color=payload.color,
                is_active=payload.is_active,
            )
            category.subcategories.extend(
                Subcategory(
                    name=child.name,
                    icon=child.icon,
                    color=child.color,
                    is_active=child.is_active,
                    order=child.order,
                )
                for child in payload.subcategories
            )
            await repository.save(category)
            created += 1

    return created, ignored


async def run_seed() -> tuple[int, int]:
    engine = create_async_engine(Settings().DATABASE_URL)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            return await seed_categories(session)
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add development category examples to the existing demo user."
    )
    parser.add_argument(
        "--confirm-development",
        action="store_true",
        help="Confirm that DATABASE_URL points to the intended development database.",
    )
    args = parser.parse_args()
    if not args.confirm_development:
        parser.error(
            "refusing to connect without --confirm-development; verify DATABASE_URL "
            "first"
        )

    try:
        created, ignored = asyncio.run(run_seed())
    except SeedUserNotFoundError as error:
        print(f"Seed failed: {error}", file=sys.stderr)
        return 1
    except IntegrityError:
        print(
            "Seed failed: a concurrent or existing database constraint conflict "
            "prevented the transaction from completing.",
            file=sys.stderr,
        )
        return 1

    print(f"Category seed complete: created={created}, ignored={ignored}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
