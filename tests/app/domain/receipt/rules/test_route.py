from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi_pagination import LimitOffsetParams

from app.core.database import get_session
from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.receipt.rules.route import receipt_rule_service
from app.domain.receipt.rules.schema import (
    ReceiptRulesCreateSchema,
    ReceiptRulesSchema,
    ReceiptRulesSeedSchema,
    ReceiptRulesUpdateSchema,
)
from app.main import app
from app.shared.schemas import Message

PREFIX = "/receipts/rules"


def test_find_builds_real_service_and_repository_from_injected_session(
    client, user, profile, rules_session
):
    previous_session = app.dependency_overrides[get_session]
    rules_session.scalar.return_value = profile
    app.dependency_overrides[get_session] = lambda: rules_session
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = client.get(f"{PREFIX}/{profile.id}")
        assert response.status_code == 200
        assert response.json()["id"] == str(profile.id)
        assert response.json()["institution_code"] == profile.institution_code
        rules_session.scalar.assert_awaited_once()
        query = rules_session.scalar.await_args.args[0]
        assert profile.id in query.compile().params.values()
        assert user.id in query.compile().params.values()
        rules_session.commit.assert_not_awaited()
    finally:
        app.dependency_overrides[get_session] = previous_session
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def route_service(client, user, profile):
    response = ReceiptRulesSchema.model_validate(profile)
    service = AsyncMock()
    service.create.return_value = response
    service.find_by.return_value = response
    service.list_all.return_value = [response]
    service.update.return_value = Message(message="updated")
    service.delete.return_value = Message(message="deleted")
    service.seed_defaults.return_value = ReceiptRulesSeedSchema(created=4, skipped=0)
    app.dependency_overrides[receipt_rule_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield service
    finally:
        app.dependency_overrides.pop(receipt_rule_service, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_registered_routes_are_nested_under_receipts_and_require_auth():
    paths = app.openapi()["paths"]
    selected = {
        path: set(operations)
        for path, operations in paths.items()
        if path.startswith(PREFIX)
    }
    assert selected == {
        PREFIX: {"get", "post"},
        PREFIX + "/seed": {"post"},
        PREFIX + "/{profile_id}": {"get", "put", "delete"},
    }
    for path in selected:
        for operation in paths[path].values():
            assert operation["security"]


def test_create_validates_and_delegates_complete_nested_payload(
    client, route_service, user, rule_payload
):
    payload = {
        "name": "  Meu  Banco ",
        "institution_code": " bank ",
        "identification_rules": [{"pattern": "BANK", "weight": 1}],
        "field_rules": [rule_payload],
    }
    response = client.post(PREFIX, json=payload)
    assert response.status_code == 201
    assert response.json()["scope"] == "private"
    assert "user_id" not in response.json()
    assert "profile_id" not in response.json()["field_rules"][0]
    route_service.create.assert_awaited_once_with(
        user=user, payload=ReceiptRulesCreateSchema.model_validate(payload)
    )


def test_list_filters_and_pagination_envelope(client, route_service, user, profile):
    response = client.get(
        PREFIX,
        params={
            "name": " Meu  Banco ",
            "institution_code": " bank ",
            "scope": "private",
            "offset": 2,
            "limit": 2,
        },
    )
    assert response.status_code == 200 and isinstance(response.json(), list)
    args = route_service.list_all.await_args.kwargs
    assert args["user"] is user
    filters = args["page_filter"]
    assert filters.name == "Meu Banco" and filters.institution_code == "BANK"
    assert filters.scope == "private" and filters.offset == 2 and filters.limit == 2
    route_service.list_all.return_value = CustomLimitOffsetPage[
        ReceiptRulesSchema
    ].create(
        [ReceiptRulesSchema.model_validate(profile)],
        params=LimitOffsetParams(limit=2, offset=2),
        total=5,
    )
    response = client.get(PREFIX, params={"offset": 2, "limit": 2})
    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 5
    assert response.json()["items"][0]["id"] == str(profile.id)


def test_find_update_and_delete_delegate_uuid_and_authenticated_user(
    client, route_service, user, profile, rule_payload
):
    path = f"{PREFIX}/{profile.id}"
    assert client.get(path).json()["id"] == str(profile.id)
    route_service.find_by.assert_awaited_once_with(profile_id=profile.id, user=user)
    payload = {
        "name": "Renamed",
        "field_rules": [{"id": str(profile.field_rules[0].id), **rule_payload}],
        "identification_rules": [],
    }
    response = client.put(path, json=payload)
    assert response.status_code == 200 and response.json() == {"message": "updated"}
    route_service.update.assert_awaited_once_with(
        profile_id=profile.id,
        payload=ReceiptRulesUpdateSchema.model_validate(payload),
        user=user,
    )
    assert client.delete(path).json() == {"message": "deleted"}
    route_service.delete.assert_awaited_once_with(profile_id=profile.id, user=user)


def test_seed_needs_no_body_delegates_and_reports_repeat(client, route_service, user):
    response = client.post(PREFIX + "/seed")
    assert response.status_code == 201
    assert response.json() == {"created": 4, "skipped": 0}
    route_service.seed_defaults.assert_awaited_once_with(user=user)
    route_service.seed_defaults.return_value = ReceiptRulesSeedSchema(
        created=0, skipped=4
    )
    assert client.post(PREFIX + "/seed").json() == {"created": 0, "skipped": 4}


@pytest.mark.parametrize("status", [403, 404, 409, 422, 500])
def test_service_errors_preserve_status_and_detail(
    client, route_service, profile, status
):
    route_service.update.side_effect = HTTPException(status, "domain error")
    response = client.put(f"{PREFIX}/{profile.id}", json={})
    assert response.status_code == status
    assert response.json() == {"detail": "domain error"}


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_malformed_uuid_is_rejected_before_service(client, route_service, method):
    response = client.request(
        method, PREFIX + "/not-a-uuid", **({"json": {}} if method == "put" else {})
    )
    assert response.status_code == 422
    getattr(
        route_service, {"get": "find_by", "put": "update", "delete": "delete"}[method]
    ).assert_not_awaited()


@pytest.mark.parametrize(
    "payload",
    [
        {"institution_code": "BANK"},
        {"user_id": str(uuid4())},
        {"field_rules": None},
        {"identification_rules": None},
        {
            "field_rules": [
                {
                    "field_name": "due_date",
                    "configuration": {
                        "strategy": "regex",
                        "patterns": [r"Vencimento (\d{2})"],
                        "parser": "date_month_name_pt_br",
                    },
                }
            ]
        },
    ],
)
def test_invalid_updates_are_rejected_before_service(
    client, route_service, profile, payload
):
    assert client.put(f"{PREFIX}/{profile.id}", json=payload).status_code == 422
    route_service.update.assert_not_awaited()


@pytest.mark.parametrize(
    "extra",
    [
        {"user_id": str(uuid4())},
        {"id": str(uuid4())},
        {"institution_code": None},
        {
            "field_rules": [
                {
                    "id": str(uuid4()),
                    "field_name": "category",
                    "configuration": {"strategy": "not_found"},
                }
            ]
        },
    ],
)
def test_create_rejects_managed_fields_and_shared_general(client, route_service, extra):
    response = client.post(
        PREFIX, json={"name": "Bank", "institution_code": "BANK"} | extra
    )
    assert response.status_code == 422
    route_service.create.assert_not_awaited()


@pytest.mark.parametrize(
    "params",
    [
        {"offset": -1},
        {"page": -1},
        {"limit": 0},
        {"scope": "admin"},
    ],
)
def test_invalid_query_is_rejected_before_service(client, route_service, params):
    assert client.get(PREFIX, params=params).status_code == 422
    route_service.list_all.assert_not_awaited()


@pytest.mark.parametrize("authorization", [None, "Bearer invalid-token"])
def test_all_endpoints_require_valid_credentials_without_hitting_service(
    client, authorization
):
    service = AsyncMock()
    app.dependency_overrides[receipt_rule_service] = lambda: service
    headers = {} if authorization is None else {"Authorization": authorization}
    path = f"{PREFIX}/{uuid4()}"
    try:
        for method, url in (
            ("get", PREFIX),
            ("post", PREFIX),
            ("get", path),
            ("put", path),
            ("delete", path),
            ("post", PREFIX + "/seed"),
        ):
            response = client.request(
                method,
                url,
                headers=headers,
                **({"json": {}} if method in {"put", "post"} else {}),
            )
            assert response.status_code == 401
        assert not service.mock_calls
    finally:
        app.dependency_overrides.pop(receipt_rule_service, None)
