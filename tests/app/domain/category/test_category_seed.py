from __future__ import annotations

from datetime import datetime, timezone
import sys
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.domain.category.repository import CategoryRepository
from app.models import Category, Role, Subcategory, User
from scripts.seed_categories import (
    SEED_USER_EMAIL,
    SeedUserNotFoundError,
    main,
    seed_categories,
)


async def create_seed_user(session):
    suffix = uuid4().hex
    role = Role(
        name=f"Seed role {suffix}",
        name_code=f"seed_role_{suffix}",
        description="Test role",
    )
    user = User(
        role_id=role.id,
        name="Existing development user",
        email=SEED_USER_EMAIL,
        username=f"seed-user-{suffix}",
        date_of_birth=datetime(1990, 1, 1, tzinfo=timezone.utc),
    )
    session.add(role)
    session.add(user)
    await session.commit()
    return user


@pytest.mark.asyncio
@pytest.mark.integration
async def test_seed_is_idempotent_and_preserves_existing_aggregate(
    category_session_factory,
):
    async with category_session_factory() as session:
        user = await create_seed_user(session)
        preexisting = Category(
            user_id=user.id,
            name="Alimentacao",
            icon="keep-icon",
            color=None,
            is_active=False,
        )
        preexisting.subcategories.append(Subcategory(name="Keep child", order=1))
        repository = CategoryRepository(session)
        async with repository.transaction():
            await repository.save(preexisting)

        first_result = await seed_categories(session)
        second_result = await seed_categories(session)

        assert first_result == (4, 1)
        assert second_result == (0, 5)

    async with category_session_factory() as verify_session:
        categories = list(
            (
                await verify_session.scalars(
                    select(Category).where(Category.user_id == user.id)
                )
            ).all()
        )
        assert len(categories) == 5
        existing = await CategoryRepository(verify_session).find_by_name(
            name="Alimentacao", user_id=user.id
        )
        assert existing.icon == "keep-icon"
        assert existing.is_active is False
        assert [child.name for child in existing.subcategories] == ["Keep child"]
        assert all(len(category.subcategories) >= 1 for category in categories)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_missing_seed_user_fails_before_category_writes(category_session_factory):
    async with category_session_factory() as session:
        with pytest.raises(SeedUserNotFoundError, match=SEED_USER_EMAIL):
            await seed_categories(session)

        category_count = await session.scalar(select(func.count(Category.id)))
        assert category_count == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_seed_rolls_back_every_example_when_a_later_save_fails(
    category_session_factory, monkeypatch
):
    async with category_session_factory() as session:
        await create_seed_user(session)
        original_save = CategoryRepository.save
        call_count = 0

        async def fail_on_second_save(self, entity, reconciliation=None):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("simulated seed failure")
            return await original_save(self, entity, reconciliation)

        monkeypatch.setattr(CategoryRepository, "save", fail_on_second_save)
        with pytest.raises(RuntimeError, match="simulated seed failure"):
            await seed_categories(session)

    async with category_session_factory() as verify_session:
        category_count = await verify_session.scalar(select(func.count(Category.id)))
        child_count = await verify_session.scalar(select(func.count(Subcategory.id)))
        assert category_count == 0
        assert child_count == 0


def test_seed_requires_explicit_development_confirmation(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["seed_categories"])

    with pytest.raises(SystemExit) as error:
        main()

    assert error.value.code == 2
