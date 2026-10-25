from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.domain.receipt.rules.business import build_reconciliation_plan
from app.domain.receipt.rules.field.schema import ReceiptFieldRuleReconcileSchema
from app.domain.receipt.rules.identification.schema import (
    ReceiptIdentificationRuleReconcileSchema,
)
from app.domain.receipt.rules.repository import ReceiptRulesRepository
from app.domain.receipt.rules.schema import ReceiptRulesFilter
from app.models import ReceiptFieldRule, ReceiptIdentificationRule

pytestmark = pytest.mark.asyncio
MODULE = "app.domain.receipt.rules.repository"


def sql(query):
    return str(query.compile(dialect=postgresql.dialect())).replace("\n", " ")


@pytest.mark.parametrize("is_active", [True, False, None])
async def test_list_all_filters_activity_without_pagination(
    rules_session, profile, is_active
):
    rules_session.scalars.return_value.all.return_value = [profile]
    result = await ReceiptRulesRepository(rules_session).list_all(
        ReceiptRulesFilter(is_active=is_active, scope="private", limit=None),
        user_id=profile.user_id,
    )
    assert result == [profile]
    query = rules_session.scalars.await_args.args[0]
    statement = sql(query)
    assert profile.user_id in query.compile().params.values()
    assert "user_id =" in statement
    if is_active is None:
        assert "is_active IS" not in statement
    else:
        assert f"is_active IS {str(is_active).lower()}" in statement
    assert statement.count("user_id =") == 2
    assert "deleted_at IS NULL" in statement
    assert "LIMIT" not in statement
    assert len(query._with_options) == 2


async def test_transaction_commits_once_and_adopts_autobegin(rules_session):
    repo = ReceiptRulesRepository(rules_session)
    async with repo.transaction():
        pass
    rules_session.begin.assert_awaited_once()
    rules_session.commit.assert_awaited_once()
    rules_session.rollback.assert_not_awaited()
    assert rules_session.info == {}
    rules_session.reset_mock()
    rules_session.in_transaction.return_value = True
    async with repo.transaction():
        pass
    rules_session.begin.assert_not_awaited()
    rules_session.commit.assert_awaited_once()


@pytest.mark.parametrize("failure_at", ["body", "commit"])
async def test_transaction_rolls_back_and_can_be_reused(rules_session, failure_at):
    repo = ReceiptRulesRepository(rules_session)
    if failure_at == "commit":
        rules_session.commit.side_effect = RuntimeError("commit failure")
    with pytest.raises(RuntimeError):
        async with repo.transaction():
            if failure_at == "body":
                raise RuntimeError("child failure")
    rules_session.rollback.assert_awaited_once()
    assert rules_session.info == {}
    rules_session.commit.side_effect = None
    async with repo.transaction():
        pass


async def test_transaction_preserves_original_exception_if_rollback_fails(
    rules_session,
):
    rules_session.rollback.side_effect = RuntimeError("rollback error")
    with patch(f"{MODULE}.logger") as logger:
        with pytest.raises(ValueError, match="original"):
            async with ReceiptRulesRepository(rules_session).transaction():
                raise ValueError("original")
    logger.exception.assert_called_once()
    assert rules_session.info == {}


async def test_transaction_rejects_nested_contexts_and_savepoints(rules_session):
    repo = ReceiptRulesRepository(rules_session)
    async with repo.transaction():
        with pytest.raises(RuntimeError, match="Nested"):
            async with repo.transaction():
                pass
    rules_session.in_nested_transaction.return_value = True
    with pytest.raises(RuntimeError, match="Nested"):
        async with repo.transaction():
            pass


async def test_mutations_and_locks_require_transaction(rules_session, profile):
    repo = ReceiptRulesRepository(rules_session)
    for operation in (
        lambda: repo.save(profile),
        lambda: repo.delete(profile),
        repo.lock_seed,
        lambda: repo.find_by(id=profile.id, user_id=profile.user_id, for_update=True),
    ):
        with pytest.raises(RuntimeError, match="transaction"):
            await operation()
    rules_session.flush.assert_not_awaited()
    rules_session.execute.assert_not_awaited()


async def test_find_locks_root_before_reloading_and_missing_lock_returns_none(
    rules_session, profile
):
    repo = ReceiptRulesRepository(rules_session)
    rules_session.scalar.side_effect = [profile, profile]
    async with repo.transaction():
        found = await repo.find_by(
            id=profile.id, user_id=profile.user_id, for_update=True
        )
    assert found is profile
    first, second = [call.args[0] for call in rules_session.scalar.await_args_list]
    assert "FOR UPDATE OF receipt_interpretation_profiles" in sql(first)
    assert "FOR UPDATE" not in sql(second)
    assert second.get_execution_options()["populate_existing"]
    assert "user_id IS NULL" in sql(first)
    assert "deleted_at IS NULL" in sql(first)
    rules_session.scalar.reset_mock(side_effect=True)
    rules_session.scalar.return_value = None
    async with repo.transaction():
        assert (
            await repo.find_by(id=profile.id, user_id=profile.user_id, for_update=True)
            is None
        )
    rules_session.scalar.assert_awaited_once()


async def test_find_without_lock_is_scoped_to_owner_or_general(rules_session, profile):
    rules_session.scalar.return_value = profile
    repo = ReceiptRulesRepository(rules_session)
    assert await repo.find_by(id=profile.id, user_id=profile.user_id) is profile
    query = rules_session.scalar.await_args.args[0]
    compiled = query.compile(dialect=postgresql.dialect())
    assert profile.id in compiled.params.values()
    assert profile.user_id in compiled.params.values()
    assert "user_id IS NULL" in str(compiled)
    assert "FOR UPDATE" not in str(compiled)


@pytest.mark.parametrize("scope", [None, "system", "private"])
async def test_list_combines_filters_with_visibility_and_orders_roots(
    rules_session, profile, scope
):
    rules_session.scalars.return_value.all.return_value = [profile]
    filters = ReceiptRulesFilter(
        name="Banco", institution_code="BANK", scope=scope, limit=1
    )
    result = await ReceiptRulesRepository(rules_session).list_all(
        filters, user_id=profile.user_id
    )
    assert result == [profile]
    query = rules_session.scalars.await_args.args[0]
    compiled = query.compile(dialect=postgresql.dialect())
    statement = sql(query)
    assert "(receipt_interpretation_profiles.user_id =" in statement
    assert "OR receipt_interpretation_profiles.user_id IS NULL)" in statement
    assert "Banco" in compiled.params.values()
    assert "BANK" in compiled.params.values()
    assert (
        "ORDER BY receipt_interpretation_profiles.created_at, receipt_interpretation_profiles.id"
        in statement
    )
    assert "LIMIT" not in statement  # limit alone keeps list semantics
    assert "JOIN" not in statement
    rules_session.scalar.assert_not_awaited()


@pytest.mark.parametrize(
    "filters,offset",
    [
        ({"page": 2, "limit": 2}, 2),
        ({"offset": 3, "limit": 2}, 3),
    ],
)
async def test_pagination_counts_roots_separately(
    rules_session, profile, filters, offset
):
    rules_session.scalar.return_value = 7
    rules_session.scalars.return_value.all.return_value = [profile]
    result = await ReceiptRulesRepository(rules_session).list_all(
        ReceiptRulesFilter(**filters), user_id=profile.user_id
    )
    assert result.items == [profile]
    assert result.meta.total == 7
    assert result.meta.offset == offset
    count = rules_session.scalar.await_args.args[0]
    assert "count(receipt_interpretation_profiles.id)" in sql(count)
    assert "JOIN" not in sql(count)
    query = rules_session.scalars.await_args.args[0]
    assert "LIMIT" in sql(query) and "OFFSET" in sql(query)


async def test_empty_page_preserves_zero_total(rules_session, user):
    rules_session.scalar.return_value = 0
    result = await ReceiptRulesRepository(rules_session).list_all(
        ReceiptRulesFilter(offset=0), user_id=user.id
    )
    assert result.items == []
    assert result.meta.total == 0


async def test_identity_queries_distinguish_shared_private_and_excluded_id(
    rules_session, user
):
    repo = ReceiptRulesRepository(rules_session)
    await repo.find_by_code(user_id=None, institution_code=None)
    statement = sql(rules_session.scalar.await_args.args[0])
    assert "user_id IS NULL" in statement and "institution_code IS NULL" in statement
    await repo.find_by_code(user_id=user.id, institution_code="BANK")
    params = rules_session.scalar.await_args.args[0].compile().params
    assert user.id in params.values() and "BANK" in params.values()
    excluded = uuid4()
    await repo.find_by_name(name="Bank", user_id=user.id, exclude_id=excluded)
    query = rules_session.scalar.await_args.args[0]
    assert "id !=" in sql(query)
    assert excluded in query.compile().params.values()


async def test_save_swaps_fields_in_two_flushes_without_intermediate_commit(
    rules_session, profile
):
    repo = ReceiptRulesRepository(rules_session)
    first = profile.field_rules[0]
    second = ReceiptFieldRule(
        profile_id=profile.id,
        field_name="beneficiary",
        configuration=first.configuration.copy(),
    )
    historical = ReceiptFieldRule(
        profile_id=profile.id,
        field_name="payer",
        configuration=first.configuration.copy(),
    )
    historical.deleted_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
    profile.field_rules.extend([second, historical])
    entries = [
        ReceiptFieldRuleReconcileSchema(
            id=first.id, field_name="beneficiary", configuration=first.configuration
        ),
        ReceiptFieldRuleReconcileSchema(
            id=second.id, field_name="payer", configuration=second.configuration
        ),
    ]
    observations = []

    async def flush():
        observations.append(
            [(c.id, c.field_name, c.deleted_at) for c in profile.field_rules]
        )

    rules_session.flush.side_effect = flush
    async with repo.transaction():
        await repo.save(
            profile, fields=build_reconciliation_plan(entries, [first.id, second.id])
        )
        rules_session.commit.assert_not_awaited()
    assert all(item[2] is not None for item in observations[0][:2])
    assert [item[1] for item in observations[1][:2]] == ["beneficiary", "payer"]
    assert all(item[2] is None for item in observations[1][:2])
    assert historical.deleted_at == datetime(2020, 1, 1, tzinfo=timezone.utc)
    rules_session.commit.assert_awaited_once()


async def test_save_replaces_removed_field_reconciles_identification_and_updates_timestamp(
    rules_session, profile
):
    repo = ReceiptRulesRepository(rules_session)
    first = profile.field_rules[0]
    identification = profile.identification_rules[0]
    removed = ReceiptIdentificationRule(profile_id=profile.id, pattern="OLD", weight=1)
    profile.identification_rules.append(removed)
    field_plan = build_reconciliation_plan(
        [
            ReceiptFieldRuleReconcileSchema(
                field_name="payer", configuration=first.configuration
            )
        ],
        [first.id],
    )
    identification_plan = build_reconciliation_plan(
        [
            ReceiptIdentificationRuleReconcileSchema(
                id=identification.id, pattern="UPDATED", weight=2
            ),
            ReceiptIdentificationRuleReconcileSchema(pattern="NEW", weight=3),
        ],
        [identification.id, removed.id],
    )
    with patch(f"{MODULE}.inspect", return_value=MagicMock(persistent=True)):
        async with repo.transaction():
            await repo.save(
                profile, fields=field_plan, identification=identification_plan
            )
    assert first.deleted_at is not None and not first.is_active
    assert profile.field_rules[-1].id != first.id
    assert profile.field_rules[-1].profile_id == profile.id
    assert identification.pattern == "UPDATED" and identification.weight == 2
    assert removed.deleted_at is not None and not removed.is_active
    assert profile.identification_rules[-1].pattern == "NEW"
    assert profile.updated_at is not None
    assert isinstance(profile.field_rules[-1].configuration, dict)


async def test_save_empty_collections_and_delete_preserve_historical_timestamps(
    rules_session, profile
):
    repo = ReceiptRulesRepository(rules_session)
    field = profile.field_rules[0]
    async with repo.transaction():
        await repo.save(
            profile,
            fields=build_reconciliation_plan([], [field.id]),
            identification=build_reconciliation_plan(
                [], [profile.identification_rules[0].id]
            ),
        )
    original_deleted = field.deleted_at
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with patch(f"{MODULE}.utcnow", return_value=now):
        async with repo.transaction():
            await repo.delete(profile)
    assert profile.deleted_at == now
    assert not profile.is_active
    assert field.deleted_at == original_deleted
    assert not field.is_active


async def test_delete_deactivates_root_and_live_children_with_same_timestamp(
    rules_session, profile
):
    async with ReceiptRulesRepository(rules_session).transaction():
        await ReceiptRulesRepository(rules_session).delete(profile)
    assert all(
        not item.is_active
        and item.deleted_at == profile.deleted_at
        and item.updated_at == profile.updated_at
        for item in (*profile.field_rules, *profile.identification_rules)
    )


async def test_lock_seed_is_transaction_scoped(rules_session):
    repo = ReceiptRulesRepository(rules_session)
    async with repo.transaction():
        await repo.lock_seed()
        rules_session.commit.assert_not_awaited()
    assert "pg_advisory_xact_lock" in str(rules_session.execute.await_args.args[0])


async def test_save_reconciles_first_field_on_profile_without_existing_fields(
    rules_session, profile
):
    profile.field_rules.clear()
    entry = ReceiptFieldRuleReconcileSchema(
        field_name="category", configuration={"strategy": "not_found"}
    )
    repo = ReceiptRulesRepository(rules_session)
    async with repo.transaction():
        await repo.save(profile, fields=build_reconciliation_plan([entry], []))
    assert len(profile.field_rules) == 1
    assert profile.field_rules[0].field_name == "category"
    assert profile.field_rules[0].profile_id == profile.id
    assert profile.field_rules[0].deleted_at is None


async def test_find_by_name_without_excluded_id_keeps_owner_and_live_filters(
    rules_session, user
):
    await ReceiptRulesRepository(rules_session).find_by_name(
        name="Bank", user_id=user.id
    )
    query = rules_session.scalar.await_args.args[0]
    statement = sql(query)
    assert "id !=" not in statement
    assert "deleted_at IS NULL" in statement
    assert user.id in query.compile().params.values()
    assert "Bank" in query.compile().params.values()


async def test_save_identification_only_preserves_existing_field_rules(
    rules_session, profile
):
    original_fields = list(profile.field_rules)
    original_configuration = profile.field_rules[0].configuration.copy()
    entry = ReceiptIdentificationRuleReconcileSchema(
        id=profile.identification_rules[0].id, pattern="UPDATED", weight=10
    )
    repo = ReceiptRulesRepository(rules_session)
    async with repo.transaction():
        await repo.save(
            profile,
            identification=build_reconciliation_plan([entry], [entry.id]),
        )
    assert profile.field_rules == original_fields
    assert profile.field_rules[0].configuration == original_configuration
    assert profile.field_rules[0].deleted_at is None
    assert profile.identification_rules[0].pattern == "UPDATED"
    assert profile.identification_rules[0].weight == 10
