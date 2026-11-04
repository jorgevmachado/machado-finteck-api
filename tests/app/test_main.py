from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest
from fastapi import HTTPException

from app.core.security import get_current_user
from app.domain.account.route import account_service
from app.domain.category.route import category_service
from app.domain.credit_card.route import credit_card_service
from app.domain.institution.route import institution_service
from app.domain.transaction.route import transaction_service
from app.domain.transaction.schema import TransactionSeedRequestSchema
from app.domain.transaction.service import TransactionService
from app.main import app
from app.main import read_root
from app.seed import SeedRequestSchema


def test_root_should_return_hello_world():
    assert read_root() == {"message": "Hello World!"}


def test_seed_request_preserves_one_offs_when_serialized_and_revalidated():
    data = {
        "transactions": {
            "one_offs": 20,
            "recurrences": 2,
            "installment_plans": 3,
            "months": 4,
            "seed": 42,
        }
    }
    request = SeedRequestSchema.model_validate(data)
    assert request.transactions.one_offs == 20
    assert request.model_dump() == data
    assert SeedRequestSchema.model_validate(request.model_dump()) == request
    assert SeedRequestSchema.model_validate_json(request.model_dump_json()) == request


@pytest.fixture
def seed_services():
    services = Mock()
    for name in (
        "accounts",
        "credit_cards",
        "institutions",
        "categories",
        "transactions",
    ):
        services.attach_mock(AsyncMock(), name)
    services.accounts.seed_defaults.return_value = SimpleNamespace(created=14)
    services.credit_cards.seed_defaults.return_value = SimpleNamespace(created=12)
    services.institutions.seed_defaults.return_value = SimpleNamespace(created=13)
    services.categories.seed_defaults.return_value = SimpleNamespace(created=14)
    services.categories.count_subcategories.side_effect = [3, 83]
    services.transactions.seed.return_value = SimpleNamespace(
        transactions=20, transaction_series=4, scheduled_transactions=30
    )
    return services


@pytest.fixture
def seed_client(client, seed_services, user):
    app.dependency_overrides[get_current_user] = lambda: user

    def override(service):
        def dependency():
            return service

        return dependency

    for factory, service in (
        (account_service, seed_services.accounts),
        (credit_card_service, seed_services.credit_cards),
        (institution_service, seed_services.institutions),
        (category_service, seed_services.categories),
        (transaction_service, seed_services.transactions),
    ):
        app.dependency_overrides[factory] = override(service)
    return client


def test_seed_runs_in_order_and_returns_created_counts(
    seed_client, seed_services, user
):
    payload = TransactionSeedRequestSchema(
        transactions=20, recurrences=2, installment_plans=2, seed=42
    )
    data = payload.model_dump()
    data["one_offs"] = data.pop("transactions")
    response = seed_client.post("/seed", json={"transactions": data})
    assert response.status_code == 200
    assert response.json() == {
        "account": 14,
        "credit_card": 12,
        "institution": 13,
        "category": 14,
        "subcategory": 80,
        "transaction": 20,
        "transaction_series": 4,
        "scheduled_transaction": 30,
    }
    assert seed_services.mock_calls == [
        call.accounts.seed_defaults(user=user),
        call.credit_cards.seed_defaults(user=user),
        call.institutions.seed_defaults(user=user),
        call.categories.count_subcategories(user=user),
        call.categories.seed_defaults(user=user),
        call.categories.count_subcategories(user=user),
        call.transactions.seed(user=user, payload=payload),
    ]
    assert (
        seed_services.transactions.seed.await_args.kwargs["payload"].model_dump()
        == payload.model_dump()
    )


def test_seed_repeated_defaults_report_zero_created(seed_client, seed_services):
    for service in (
        seed_services.accounts,
        seed_services.credit_cards,
        seed_services.institutions,
        seed_services.categories,
    ):
        service.seed_defaults.return_value = SimpleNamespace(created=0)
    seed_services.categories.count_subcategories.side_effect = [83, 83]
    response = seed_client.post("/seed", json={})
    assert response.status_code == 200
    assert all(
        response.json()[name] == 0
        for name in ("account", "credit_card", "institution", "category", "subcategory")
    )
    assert response.json()["transaction"] == 20
    seed_services.transactions.seed.assert_awaited_once()
    assert (
        seed_services.transactions.seed.await_args.kwargs["payload"].model_dump()
        == TransactionSeedRequestSchema().model_dump()
    )


def test_seed_requires_authenticated_user(client, seed_services):
    app.dependency_overrides[account_service] = lambda: seed_services.accounts
    response = client.post("/seed", json={})
    assert response.status_code == 401
    seed_services.accounts.seed_defaults.assert_not_awaited()


@pytest.mark.parametrize(
    "body",
    [
        None,
        {"transactions": -1},
        {"transactions": {"transactions": -1}},
        {"transactions": {"transactions": 20}},
        {"transactions": {"one_offs": -1}},
        {"transactions": {"one_offs": 0, "recurrences": 0, "installment_plans": 0}},
        {"transactions": {"months": 25}},
        {"transactions": {"unexpected": True}},
        {"transactions": None},
        {"recurrences": 2, "months": 3},
    ],
)
def test_seed_rejects_missing_or_invalid_payload(seed_client, seed_services, body):
    response = seed_client.post("/seed", **({"json": body} if body is not None else {}))
    assert response.status_code == 422
    seed_services.accounts.seed_defaults.assert_not_awaited()


def test_seed_stops_at_failed_service(seed_client, seed_services):
    seed_services.credit_cards.seed_defaults.side_effect = HTTPException(
        500, "Seed failed"
    )
    response = seed_client.post("/seed", json={})
    assert response.status_code == 500
    assert response.json() == {"detail": "Seed failed"}
    seed_services.accounts.seed_defaults.assert_awaited_once()
    seed_services.institutions.seed_defaults.assert_not_awaited()
    seed_services.categories.seed_defaults.assert_not_awaited()
    seed_services.transactions.seed.assert_not_awaited()


def test_seed_leaves_admin_validation_to_transaction_service(
    seed_client, seed_services, user
):
    user.role = SimpleNamespace(name_code="user", deleted_at=None)
    repository = Mock()
    seed_services.transactions.seed.side_effect = TransactionService(repository).seed
    response = seed_client.post("/seed", json={})
    assert response.status_code == 403
    for service in (
        seed_services.accounts,
        seed_services.credit_cards,
        seed_services.institutions,
        seed_services.categories,
    ):
        service.seed_defaults.assert_awaited_once_with(user=user)
    repository.transaction.assert_not_called()
