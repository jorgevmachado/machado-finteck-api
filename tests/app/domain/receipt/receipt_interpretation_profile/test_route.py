import json
import re
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.security import get_current_user
from app.domain.receipt.receipt_interpretation_profile.route import profile_service
from app.domain.receipt.receipt_interpretation_profile.schema import (
    ReceiptInterpretationProfileCreateSchema,
    ReceiptInterpretationProfileSchema,
    ReceiptInterpretationProfileUpdateSchema,
)
from app.main import app
from app.models import ReceiptInterpretationProfile
from app.shared.schemas import Message

PREFIX = "/receipt-interpretation-profiles"


def test_exact_five_registered_routes_without_child_endpoints():
    paths = app.openapi()["paths"]
    selected = {
        path: set(methods) for path, methods in paths.items() if path.startswith(PREFIX)
    }
    assert selected == {
        PREFIX: {"get", "post"},
        f"{PREFIX}/{{profile_id}}": {"get", "put", "delete"},
    }
    for methods in (paths[PREFIX], paths[f"{PREFIX}/{{profile_id}}"]):
        assert all(operation["security"] for operation in methods.values())


def test_route_delegation_filters_validation_and_output(client, user):
    entity = ReceiptInterpretationProfile(
        user_id=user.id, name="NU", institution_code="NU"
    )
    response = ReceiptInterpretationProfileSchema.model_validate(entity)
    service = AsyncMock()
    service.create.return_value = response
    service.find_by.return_value = response
    service.list_all.return_value = [response]
    service.update.return_value = Message(message="updated")
    service.delete.return_value = Message(message="deleted")
    app.dependency_overrides[profile_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: user
    body = {"name": "  NU  ", "institution_code": " nu "}
    assert client.post(PREFIX, json=body).status_code == 201
    service.create.assert_awaited_once_with(
        user=user, payload=ReceiptInterpretationProfileCreateSchema(**body)
    )
    assert (
        client.get(
            PREFIX, params={"institution_code": " nu ", "name": "  NU "}
        ).status_code
        == 200
    )
    filters = service.list_all.await_args.kwargs["page_filter"]
    assert filters.name == filters.institution_code == "NU"
    for params in (
        {"offset": -1},
        {"limit": 0},
        {"scope": "admin"},
        {"institution_code": "NU BANK"},
    ):
        assert client.get(PREFIX, params=params).status_code == 422
    assert client.get(f"{PREFIX}/{entity.id}").json()["id"] == str(entity.id)
    assert client.put(f"{PREFIX}/{entity.id}", json={}).json() == {"message": "updated"}
    assert client.delete(f"{PREFIX}/{entity.id}").json() == {"message": "deleted"}
    readme = Path(
        "app/domain/receipt/receipt_interpretation_profile/README.md"
    ).read_text()
    examples = [
        json.loads(example)
        for example in re.findall(r"```json\n(.*?)\n```", readme, flags=re.DOTALL)
    ]
    assert client.post(PREFIX, json=examples[0]).status_code == 201
    service.create.assert_awaited_with(
        user=user,
        payload=ReceiptInterpretationProfileCreateSchema.model_validate(examples[0]),
    )
    for example in examples[1:]:
        assert client.put(f"{PREFIX}/{entity.id}", json=example).status_code == 200
        service.update.assert_awaited_with(
            profile_id=entity.id,
            payload=ReceiptInterpretationProfileUpdateSchema.model_validate(example),
            user=user,
        )


@pytest.mark.parametrize("authorization", [None, "Bearer invalid-token"])
def test_all_endpoints_require_credentials(client, authorization):
    headers = {} if authorization is None else {"Authorization": authorization}
    path = f"{PREFIX}/{uuid4()}"
    for method, url, payload in (
        ("get", PREFIX, None),
        ("post", PREFIX, {}),
        ("get", path, None),
        ("put", path, {}),
        ("delete", path, None),
    ):
        response = client.request(
            method,
            url,
            headers=headers,
            **({"json": payload} if payload is not None else {}),
        )
        assert response.status_code == 401
