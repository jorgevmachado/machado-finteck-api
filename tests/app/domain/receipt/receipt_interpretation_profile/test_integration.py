import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError

from app.core.database import get_session
from app.core.security import get_current_user
from app.domain.receipt.receipt_interpretation_profile.business import (
    build_reconciliation_plan,
)
from app.domain.receipt.receipt_interpretation_profile.repository import (
    ReceiptInterpretationProfileRepository as Repository,
)
from app.domain.receipt.receipt_interpretation_profile.route import router
from app.domain.receipt.receipt_interpretation_profile.schema import (
    ReceiptFieldRuleReconcileSchema,
    ReceiptInterpretationProfileCreateSchema as Create,
    ReceiptInterpretationProfileFilter as Filter,
    ReceiptInterpretationProfileUpdateSchema as Update,
)
from app.domain.receipt.receipt_interpretation_profile.service import (
    ReceiptInterpretationProfileService as Service,
)
from app.models import (
    ReceiptFieldRule,
    ReceiptIdentificationRule,
    ReceiptInterpretationProfile,
)
from tests.app.domain.receipt.receipt_interpretation_profile.conftest import create_user
from tests.app.domain.receipt.receipt_interpretation_profile.test_schema import (
    field_payload,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
PREFIX = "/receipt-interpretation-profiles"


def payload(code="NUBANK"):
    return Create(
        name=f"Meu {code}",
        institution_code=code,
        identification_rules=[{"pattern": r"\bNU\b", "weight": 100}],
        field_rules=[
            field_payload("payer", "text"),
            field_payload("beneficiary", "text"),
        ],
    )


async def test_reads_filter_visibility_pagination_and_eager_queries(profile_sessions):
    async with profile_sessions() as session:
        owner = await create_user(session)
        other = await create_user(session)
        service = Service.from_session(session)
        assert await service.list_all(Filter(), owner) == []
        first = await service.create(owner, payload())
        second = await service.create(owner, payload("ITAU"))
        await service.create(other, payload("FOREIGN"))
        general = ReceiptInterpretationProfile(
            user_id=None, name="Geral", institution_code=None, is_active=False
        )
        async with service.repository.transaction():
            await service.repository.save(general)
        deleted_child = await session.get(ReceiptFieldRule, first.field_rules[0].id)
        from app.models.common import utcnow

        deleted_child.deleted_at = utcnow()
        await session.commit()
        statements = []

        def capture(*args):
            statements.append(args[2])

        event.listen(session.bind.sync_engine, "before_cursor_execute", capture)
        try:
            all_profiles = await service.list_all(Filter(limit=1), owner)
        finally:
            event.remove(session.bind.sync_engine, "before_cursor_execute", capture)
        assert [p.id for p in all_profiles] == [first.id, second.id, general.id]
        assert len(all_profiles[0].field_rules) == 1
        assert not all_profiles[-1].is_active
        assert len(statements) == 3
        assert len(await service.list_all(Filter(scope="system"), owner)) == 1
        assert len(await service.list_all(Filter(scope="private"), owner)) == 2
        assert (
            len(await service.list_all(Filter(institution_code=" nubank "), owner)) == 1
        )
        assert len(await service.list_all(Filter(name="  Meu  NUBANK "), owner)) == 1
        assert (
            await service.list_all(Filter(scope="system", name="Meu NUBANK"), owner)
            == []
        )
        page = await service.list_all(Filter(offset=1, limit=1), owner)
        assert page.meta.total == 3
        assert page.items[0].id == second.id
        assert (await service.list_all(Filter(page=1, limit=2), owner)).meta.total == 3
        assert (await service.list_all(Filter(offset=999), owner)).items == []


async def test_http_contracts_ownership_general_and_put(profile_sessions):
    async with profile_sessions() as session:
        owner = await create_user(session)
        foreign = await create_user(session)
        general = ReceiptInterpretationProfile(
            user_id=None, name="Geral", institution_code=None
        )
        async with Repository(session).transaction():
            await Repository(session).save(general)
        general_id = general.id
    app = FastAPI()
    app.include_router(router, prefix=PREFIX)

    async def session_override():
        async with profile_sessions() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_current_user] = lambda: owner
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(PREFIX, json=payload().model_dump(mode="json"))
        assert response.status_code == 201, response.text
        root = response.json()
        profile_id = root["id"]
        assert root["scope"] == "private"
        assert "user_id" not in root
        assert "profile_id" not in root["field_rules"][0]
        assert (
            await client.post(PREFIX, json=payload().model_dump(mode="json"))
        ).status_code == 409
        assert (await client.get(PREFIX, params={"limit": 1})).json()[0][
            "scope"
        ] == "system"
        assert (await client.get(PREFIX, params={"offset": 0, "limit": 1})).json()[
            "meta"
        ]["total"] == 2
        assert (
            await client.put(f"{PREFIX}/{profile_id}", json={"name": "Novo"})
        ).status_code == 200
        unchanged = (await client.get(f"{PREFIX}/{profile_id}")).json()
        assert unchanged["field_rules"] == root["field_rules"]
        first, second = root["field_rules"]
        mixed = {
            "field_rules": [
                {"id": first["id"], **field_payload("payer", "text")},
                field_payload("description", "text"),
            ]
        }
        assert (
            await client.put(f"{PREFIX}/{profile_id}", json=mixed)
        ).status_code == 200
        children = (await client.get(f"{PREFIX}/{profile_id}")).json()["field_rules"]
        assert {c["field_name"] for c in children} == {"payer", "description"}
        assert (
            await client.put(
                f"{PREFIX}/{profile_id}",
                json={
                    "field_rules": [
                        {"id": second["id"], **field_payload("beneficiary", "text")}
                    ]
                },
            )
        ).status_code == 422
        assert (
            await client.put(
                f"{PREFIX}/{profile_id}",
                json={"field_rules": [], "identification_rules": []},
            )
        ).status_code == 200
        empty = (await client.get(f"{PREFIX}/{profile_id}")).json()
        assert empty["field_rules"] == empty["identification_rules"] == []
        for body in (
            {"user_id": str(foreign.id)},
            {"institution_code": "NUBANK"},
            {"field_rules": None},
        ):
            assert (
                await client.put(f"{PREFIX}/{profile_id}", json=body)
            ).status_code == 422
        assert (
            await client.post(
                PREFIX,
                json=payload().model_dump(mode="json") | {"user_id": str(owner.id)},
            )
        ).status_code == 422
        assert (await client.get(f"{PREFIX}/invalid-uuid")).status_code == 422
        assert (await client.get(f"{PREFIX}/{uuid4()}")).status_code == 404
        assert (await client.get(f"{PREFIX}/{general_id}")).json()["scope"] == "system"
        for method, body in (("put", {}), ("delete", None)):
            response = await client.request(
                method,
                f"{PREFIX}/{general_id}",
                **({"json": body} if body is not None else {}),
            )
            assert response.status_code == 403
        app.dependency_overrides[get_current_user] = lambda: foreign
        for method in ("get", "put", "delete"):
            response = await client.request(
                method,
                f"{PREFIX}/{profile_id}",
                **({"json": {}} if method == "put" else {}),
            )
            assert response.status_code == 404
        app.dependency_overrides[get_current_user] = lambda: owner
        assert (await client.delete(f"{PREFIX}/{profile_id}")).status_code == 200
        assert (await client.get(f"{PREFIX}/{profile_id}")).status_code == 404
        assert (
            await client.post(PREFIX, json=payload().model_dump(mode="json"))
        ).status_code == 201
        app.dependency_overrides.pop(get_current_user)
        for method, path in (
            ("get", PREFIX),
            ("post", PREFIX),
            ("get", f"{PREFIX}/{profile_id}"),
            ("put", f"{PREFIX}/{profile_id}"),
            ("delete", f"{PREFIX}/{profile_id}"),
        ):
            response = await client.request(method, path, json={})
            assert response.status_code == 401


async def test_swaps_replacement_delete_and_historical_timestamps(profile_sessions):
    async with profile_sessions() as session:
        user = await create_user(session)
        service = Service.from_session(session)
        profile = await service.create(user, payload())
        first, second = profile.field_rules
        await service.update(
            profile.id,
            Update(
                field_rules=[
                    {"id": first.id, **field_payload("beneficiary", "text")},
                    {"id": second.id, **field_payload("payer", "text")},
                ]
            ),
            user,
        )
        swapped = await service.find_by(profile.id, user)
        assert [(c.id, c.field_name) for c in swapped.field_rules] == [
            (first.id, "beneficiary"),
            (second.id, "payer"),
        ]
        await service.update(
            profile.id, Update(field_rules=[field_payload("payer", "text")]), user
        )
        old = await session.get(ReceiptFieldRule, second.id)
        deleted_at = old.deleted_at
        assert deleted_at is not None
        await service.delete(profile.id, user)
        await session.refresh(old)
        assert old.deleted_at == deleted_at
        root = await session.get(ReceiptInterpretationProfile, profile.id)
        live_deleted = (
            await session.scalars(
                select(ReceiptFieldRule).where(
                    ReceiptFieldRule.profile_id == profile.id
                )
            )
        ).all()
        ids = (
            await session.scalars(
                select(ReceiptIdentificationRule).where(
                    ReceiptIdentificationRule.profile_id == profile.id
                )
            )
        ).all()
        assert all(
            not c.is_active and c.deleted_at is not None
            for c in live_deleted + list(ids)
        )
        assert all(c.deleted_at == root.deleted_at for c in ids)


async def test_child_failure_and_commit_failure_rollback_reuse_session(
    profile_sessions,
):
    async with profile_sessions() as session:
        user = await create_user(session)
        user_id = user.id
        repo = Repository(session)
        entity = ReceiptInterpretationProfile(
            user_id=user_id, name="Bad", institution_code="BAD"
        )
        entity.identification_rules.append(
            ReceiptIdentificationRule(profile_id=entity.id, pattern="NU", weight=0)
        )
        with pytest.raises(IntegrityError):
            async with repo.transaction():
                await repo.save(entity)
        assert await session.get(ReceiptInterpretationProfile, entity.id) is None
        good = ReceiptInterpretationProfile(
            user_id=user_id, name="Good", institution_code="GOOD"
        )
        async with repo.transaction():
            await repo.save(good)
        profile_id = good.id
        with patch.object(
            session, "commit", AsyncMock(side_effect=RuntimeError("commit failed"))
        ):
            with pytest.raises(RuntimeError, match="commit failed"):
                async with repo.transaction():
                    locked = await repo.find_by(
                        id=profile_id, user_id=user_id, for_update=True
                    )
                    locked.name = "Wrong"
                    await repo.save(locked)
        assert (await repo.find_by(id=profile_id, user_id=user_id)).name == "Good"
        async with repo.transaction():
            with pytest.raises(RuntimeError, match="Nested"):
                async with repo.transaction():
                    pass


async def test_failure_between_reconciliation_phases_is_atomic(profile_sessions):
    async with profile_sessions() as session:
        user = await create_user(session)
        user_id = user.id
        profile = await Service.from_session(session).create(user, payload())
        repo = Repository(session)
        original_flush = session.flush
        calls = 0

        async def failing_flush(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("second phase")
            return await original_flush(*args, **kwargs)

        with pytest.raises(RuntimeError, match="second phase"):
            async with repo.transaction():
                entity = await repo.find_by(
                    id=profile.id, user_id=user_id, for_update=True
                )
                entries = [
                    ReceiptFieldRuleReconcileSchema(
                        id=profile.field_rules[0].id,
                        **field_payload("beneficiary", "text"),
                    ),
                    ReceiptFieldRuleReconcileSchema(
                        id=profile.field_rules[1].id, **field_payload("payer", "text")
                    ),
                ]
                plan = build_reconciliation_plan(
                    entries, [c.id for c in entity.field_rules]
                )
                with patch.object(session, "flush", failing_flush):
                    await repo.save(entity, fields=plan)
        reloaded = await repo.find_by(id=profile.id, user_id=user_id)
        assert {c.id: c.field_name for c in reloaded.field_rules} == {
            c.id: c.field_name for c in profile.field_rules
        }


async def test_concurrent_duplicate_code_maps_real_constraint_to_409(profile_sessions):
    async with profile_sessions() as session:
        user = await create_user(session)
    barrier = asyncio.Barrier(2)

    async def create():
        async with profile_sessions() as session:
            service = Service.from_session(session)
            original = service.repository.find_by_code

            async def synchronize(**kwargs):
                result = await original(**kwargs)
                await asyncio.wait_for(barrier.wait(), 10)
                return result

            service.repository.find_by_code = synchronize
            try:
                return await service.create(user, payload())
            except HTTPException as exception:
                return exception.status_code

    results = await asyncio.wait_for(asyncio.gather(create(), create()), 20)
    assert sum(isinstance(result, int) and result == 409 for result in results) == 1
    assert sum(not isinstance(result, int) for result in results) == 1


async def test_root_lock_reloads_children_and_rejects_stale_id(profile_sessions):
    async with profile_sessions() as session:
        user = await create_user(session)
        profile = await Service.from_session(session).create(user, payload())
    async with profile_sessions() as writer, profile_sessions() as waiter:
        repo = Repository(writer)
        service = Service.from_session(waiter)
        await service.repository.find_by(id=profile.id, user_id=user.id)
        started = asyncio.Event()
        original_find = service.repository.find_by

        async def signal_find(**kwargs):
            started.set()
            return await original_find(**kwargs)

        service.repository.find_by = signal_find
        pending = None
        try:
            async with repo.transaction():
                entity = await repo.find_by(
                    id=profile.id, user_id=user.id, for_update=True
                )
                plan = build_reconciliation_plan([], [c.id for c in entity.field_rules])
                await repo.save(entity, fields=plan)
                pending = asyncio.create_task(
                    service.update(
                        profile.id,
                        Update(
                            field_rules=[
                                {
                                    "id": profile.field_rules[0].id,
                                    **field_payload("payer", "text"),
                                }
                            ]
                        ),
                        user,
                    )
                )
                await asyncio.wait_for(started.wait(), 5)
                await asyncio.sleep(0.1)
                assert not pending.done()
            with pytest.raises(HTTPException) as caught:
                await asyncio.wait_for(pending, 10)
            assert caught.value.status_code == 422
        finally:
            if pending is not None and not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)


async def test_migrated_general_unique_index_and_json_constraint(profile_sessions):
    async with profile_sessions() as session:
        repo = Repository(session)
        general = ReceiptInterpretationProfile(
            user_id=None, name="Geral", institution_code=None
        )
        async with repo.transaction():
            await repo.save(general)
        definition = await session.scalar(
            text(
                "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_receipt_profiles_general_live'"
            )
        )
        assert "((1))" in definition
        with pytest.raises(IntegrityError):
            async with repo.transaction():
                await repo.save(
                    ReceiptInterpretationProfile(
                        user_id=None, name="Other", institution_code=None
                    )
                )
        general_id = (await session.scalar(select(ReceiptInterpretationProfile))).id
        with pytest.raises(IntegrityError):
            async with repo.transaction():
                entity = await repo.find_by(
                    id=general_id, user_id=uuid4(), for_update=True
                )
                entity.field_rules.append(
                    ReceiptFieldRule(
                        profile_id=entity.id, field_name="payer", configuration={}
                    )
                )
                await repo.save(entity)
        assert (await session.execute(text("SELECT 1"))).scalar_one() == 1


async def test_identification_mixed_update_and_cross_collection_identity(
    profile_sessions,
):
    async with profile_sessions() as session:
        user = await create_user(session)
        service = Service.from_session(session)
        profile = await service.create(user, payload())
        other = await service.create(user, payload("ITAU"))
        first = profile.identification_rules[0]
        await service.update(
            profile.id,
            Update(
                identification_rules=[
                    {
                        "id": first.id,
                        "pattern": "NUBANK",
                        "weight": 200,
                        "is_active": False,
                    },
                    {"pattern": "NU PAGAMENTOS", "weight": 100},
                ]
            ),
            user,
        )
        updated = await service.find_by(profile.id, user)
        assert len(updated.identification_rules) == 2
        assert updated.identification_rules[0].id == first.id
        assert not updated.identification_rules[0].is_active
        assert updated.field_rules == profile.field_rules
        for invalid_id in (profile.field_rules[0].id, other.identification_rules[0].id):
            with pytest.raises(HTTPException) as caught:
                await service.update(
                    profile.id,
                    Update(
                        name="Should not change",
                        identification_rules=[
                            {"id": invalid_id, "pattern": "NU", "weight": 1}
                        ],
                    ),
                    user,
                )
            assert caught.value.status_code == 422
            await session.refresh(user)
            assert (await service.find_by(profile.id, user)).name == profile.name


async def test_failed_service_commit_does_not_read_expired_orm_metadata(
    profile_sessions,
):
    async with profile_sessions() as session:
        user = await create_user(session)
        service = Service.from_session(session)
        from sqlalchemy import inspect

        with patch(
            "app.domain.receipt.receipt_interpretation_profile.service.log_service_success"
        ) as success:
            with patch.object(
                session,
                "commit",
                AsyncMock(side_effect=RuntimeError("failed commit")),
            ):
                with pytest.raises(HTTPException) as caught:
                    await service.create(user, payload())
        assert caught.value.status_code == 500
        assert isinstance(caught.value.__cause__, RuntimeError)
        assert inspect(user).expired
        success.assert_not_called()
        assert (
            list((await session.scalars(select(ReceiptInterpretationProfile))).all())
            == []
        )
