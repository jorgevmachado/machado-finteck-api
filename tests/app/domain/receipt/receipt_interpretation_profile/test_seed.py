from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.domain.receipt.receipt_interpretation_profile.repository import (
    ReceiptInterpretationProfileRepository,
)
from app.domain.receipt.receipt_interpretation_profile.seed import (
    load_seed_profiles,
    main,
    seed_profiles,
)
from app.models import ReceiptFieldRule, ReceiptInterpretationProfile
from tests.app.domain.receipt.receipt_interpretation_profile.conftest import create_user


def test_seed_command_requires_explicit_development_confirmation(monkeypatch):
    monkeypatch.setattr("sys.argv", ["seed", "--user-id", str(uuid4())])
    with pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_is_atomic_repeatable_owner_scoped_and_replace_is_explicit(
    profile_sessions,
):
    async with profile_sessions() as session:
        owner = await create_user(session)
        second = await create_user(session)
        assert await seed_profiles(session, owner.id) == (4, 0, 0)
        entities = list(
            (await session.scalars(select(ReceiptInterpretationProfile))).all()
        )
        general = next(p for p in entities if p.user_id is None)
        nubank = next(p for p in entities if p.institution_code == "NUBANK")
        assert len(general.field_rules) == 18
        assert len(nubank.field_rules) == 3
        first_rule = nubank.field_rules[0]
        original_rule_id = first_rule.id
        original_field = first_rule.field_name
        first_rule.is_active = False
        nubank.name = "Personalized"
        await session.commit()
        assert await seed_profiles(session, owner.id) == (0, 0, 4)
        assert nubank.name == "Personalized"
        assert not first_rule.is_active
        assert await seed_profiles(session, second.id) == (3, 0, 1)
        assert (
            await session.scalar(select(func.count(ReceiptInterpretationProfile.id)))
            == 7
        )
        assert await seed_profiles(session, owner.id, replace_existing=True) == (
            0,
            4,
            0,
        )
        await session.refresh(nubank)
        assert nubank.name == "Nubank"
        assert any(
            c.id == original_rule_id and c.field_name == original_field and c.is_active
            for c in nubank.field_rules
        )
        second_profiles = (
            await session.scalars(
                select(ReceiptInterpretationProfile).where(
                    ReceiptInterpretationProfile.user_id == second.id
                )
            )
        ).all()
        assert len(second_profiles) == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_seed_missing_owner_and_partial_failure_leave_no_profiles(
    profile_sessions,
):
    async with profile_sessions() as session:
        with pytest.raises(ValueError, match="owner"):
            await seed_profiles(session, uuid4())
        assert (
            await session.scalar(select(func.count(ReceiptInterpretationProfile.id)))
            == 0
        )
        owner = await create_user(session)
        original_save = ReceiptInterpretationProfileRepository.save
        calls = 0

        async def fail_second(repo, entity, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("bank save failed")
            return await original_save(repo, entity, **kwargs)

        with patch.object(ReceiptInterpretationProfileRepository, "save", fail_second):
            with pytest.raises(RuntimeError, match="bank save"):
                await seed_profiles(session, owner.id)
        assert (
            await session.scalar(select(func.count(ReceiptInterpretationProfile.id)))
            == 0
        )
        assert await session.scalar(select(func.count(ReceiptFieldRule.id))) == 0


def test_seed_files_define_one_general_and_private_codes():
    general, profiles = load_seed_profiles()
    assert general.institution_code is None
    assert general.identification_rules == []
    assert {p.institution_code for p in profiles} == {"NUBANK", "ITAU", "CAIXA"}


def test_seed_command_reports_failure_without_success(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv", ["seed", "--user-id", str(uuid4()), "--confirm-development"]
    )
    with patch(
        "app.domain.receipt.receipt_interpretation_profile.seed._run",
        AsyncMock(side_effect=ValueError("owner does not exist")),
    ):
        assert main() == 1
    assert "complete" not in capsys.readouterr().out
