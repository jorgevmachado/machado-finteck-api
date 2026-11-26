from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.exceptions import ResponseValidationError
from fastapi.testclient import TestClient
from fastapi_pagination import LimitOffsetParams

from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.receipt.route import (
    receipt_service,
    router,
    upload_receipt,
    upload_batch,
)
from app.domain.receipt.confirm_schema import ReceiptConfirmOutcome
from app.domain.receipt.schema import ReceiptSchema
from app.domain.receipt.service import ReceiptService
from app.models import ReceiptStatusEnum, utcnow
from app.shared.schemas import Message
from app.shared.utils.string import to_snake_case


@pytest.mark.asyncio
async def test_receipt_service_dependency_binds_session_and_upload_delegates(user):
    session = MagicMock()
    service = receipt_service(session)
    assert isinstance(service, ReceiptService)
    assert service.repository.session is session
    assert service.rules_service.repository.session is session
    service.upload = AsyncMock()
    file = UploadFile(file=BytesIO(b"receipt"), filename="receipt.pdf")

    result = await upload_receipt(service=service, current_user=user, file=file)

    assert result is service.upload.return_value
    service.upload.assert_awaited_once_with(file=file, user=user)

    service.batch = AsyncMock()
    result = await upload_batch(service=service, current_user=user, files=[file])
    assert result is service.batch.return_value
    service.batch.assert_awaited_once_with(files=[file], user=user)


@pytest.fixture
def service():
    return AsyncMock(spec=ReceiptService)


@pytest.fixture
def receipt():
    return ReceiptSchema(
        id=uuid4(),
        data=None,
        status=ReceiptStatusEnum.RECEIVED,
        file_name="receipt.pdf",
        file_type="application/pdf",
        file_size=7,
        created_at=utcnow(),
    )


@pytest.fixture
def payment():
    """`confirm` devolve o `Payment` criado; a rota serializa o objeto com `PaymentSchema`."""

    def named_entity(name):
        return SimpleNamespace(
            id=uuid4(),
            name=name,
            name_code=to_snake_case(name),
            created_at=utcnow(),
        )

    return SimpleNamespace(
        id=uuid4(),
        amount=Decimal("123.45"),
        payer=named_entity("Payer"),
        receipt=SimpleNamespace(
            id=uuid4(),
            status=ReceiptStatusEnum.PROCESSED,
            file_name="receipt.pdf",
            file_type="application/pdf",
            file_size=7,
            created_at=utcnow(),
        ),
        subcategory=SimpleNamespace(
            id=uuid4(),
            name="Groceries",
            icon=None,
            color=None,
            is_active=True,
            order=1,
            created_at=utcnow(),
        ),
        beneficiary=named_entity("Beneficiary"),
        payment_date=date(2026, 10, 26),
        source_institution=named_entity("Source"),
        description="Monthly payment",
        destination_institution=None,
        created_at=utcnow(),
    )


@pytest.fixture
def receipt_client(user, service):
    app = FastAPI()
    app.include_router(router, prefix="/receipts")
    app.dependency_overrides[receipt_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(
    ("query", "limit", "offset", "page"),
    [
        ("", 12, None, None),
        ("?limit=2&offset=4", 2, 4, None),
        ("?page=2&limit=2", 2, None, 2),
    ],
)
def test_list_all_returns_paginated_receipts(
    receipt_client, service, receipt, user, query, limit, offset, page
):
    result_offset = (page - 1) * limit if page is not None else (offset or 0)
    service.list_all.return_value = CustomLimitOffsetPage.create(
        [receipt], total=8, params=LimitOffsetParams(limit=limit, offset=result_offset)
    )

    response = receipt_client.get(f"/receipts{query}")

    assert response.status_code == 200
    assert response.json()["items"] == [receipt.model_dump(mode="json")]
    assert response.json()["meta"]["total"] == 8
    assert response.json()["meta"]["limit"] == limit
    assert response.json()["meta"]["offset"] == result_offset
    service.list_all.assert_awaited_once()
    kwargs = service.list_all.call_args.kwargs
    assert kwargs["user"] is user
    assert kwargs["page_filter"].limit == limit
    assert kwargs["page_filter"].offset == offset
    assert kwargs["page_filter"].page == page


def test_find_one_returns_receipt(receipt_client, service, receipt, user):
    service.find_one.return_value = receipt

    response = receipt_client.get(f"/receipts/{receipt.id}")

    assert response.status_code == 200
    assert response.json() == receipt.model_dump(mode="json")
    service.find_one.assert_awaited_once_with(receipt_id=receipt.id, user=user)


def test_find_one_propagates_not_found(receipt_client, service):
    service.find_one.side_effect = HTTPException(404, "Receipt not found")

    response = receipt_client.get(f"/receipts/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Receipt not found"}


@pytest.mark.parametrize(
    "path",
    [
        "/receipts/not-a-uuid",
    ],
)
def test_read_routes_reject_invalid_parameters(receipt_client, service, path):
    response = receipt_client.get(path)

    assert response.status_code == 422
    service.list_all.assert_not_awaited()
    service.find_one.assert_not_awaited()


@pytest.mark.parametrize("path", ["/receipts", f"/receipts/{uuid4()}"])
def test_read_routes_require_authentication(service, path):
    app = FastAPI()
    app.include_router(router, prefix="/receipts")
    app.dependency_overrides[receipt_service] = lambda: service
    with TestClient(app) as client:
        response = client.get(path)

    assert response.status_code in (401, 403)
    service.list_all.assert_not_awaited()
    service.find_one.assert_not_awaited()


def test_confirm_route_delegates_payload_and_returns_the_envelope(
    receipt_client, service, user, confirm_payload, payment
):
    receipt_id = uuid4()
    service.confirm.return_value = ReceiptConfirmOutcome(payment=payment)

    response = receipt_client.post(
        f"/receipts/{receipt_id}/confirm", json=confirm_payload.model_dump(mode="json")
    )

    assert response.status_code == 200
    body = response.json()
    assert body["payment"]["id"] == str(payment.id)
    assert body["transaction"] is None
    assert body["series"] is None
    assert body["occurrence"] is None
    service.confirm.assert_awaited_once_with(
        receipt_id=receipt_id, user=user, payload=confirm_payload
    )


def test_confirm_route_returns_409_with_the_conflict_body(
    receipt_client, service, confirm_payload
):
    service.confirm.side_effect = HTTPException(
        status_code=409,
        detail={
            "type": "OCCURRENCE_EXISTS",
            "existing": {"id": "abc", "settled_on": "2026-10-26", "value": "55.90"},
            "occurrence": {"occurrence_index": 3},
        },
    )

    response = receipt_client.post(
        f"/receipts/{uuid4()}/confirm", json=confirm_payload.model_dump(mode="json")
    )

    assert response.status_code == 409
    assert response.json()["detail"]["type"] == "OCCURRENCE_EXISTS"
    assert response.json()["detail"]["existing"]["value"] == "55.90"


@pytest.mark.parametrize("status", [404, 409, 500])
def test_confirm_route_preserves_service_errors(
    receipt_client, service, confirm_payload, status
):
    service.confirm.side_effect = HTTPException(status, "Confirmation failed")

    response = receipt_client.post(
        f"/receipts/{uuid4()}/confirm", json=confirm_payload.model_dump(mode="json")
    )

    assert response.status_code == status
    assert response.json() == {"detail": "Confirmation failed"}


@pytest.mark.parametrize("invalid", ["id", "payload"])
def test_confirm_route_rejects_invalid_input(
    receipt_client, service, confirm_payload, invalid
):
    receipt_id = "not-a-uuid" if invalid == "id" else str(uuid4())
    payload = {} if invalid == "payload" else confirm_payload.model_dump(mode="json")

    response = receipt_client.post(f"/receipts/{receipt_id}/confirm", json=payload)

    assert response.status_code == 422
    service.confirm.assert_not_awaited()


def test_confirm_route_requires_authentication(service, confirm_payload):
    app = FastAPI()
    app.include_router(router, prefix="/receipts")
    app.dependency_overrides[receipt_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            f"/receipts/{uuid4()}/confirm", json=confirm_payload.model_dump(mode="json")
        )

    assert response.status_code in (401, 403)
    service.confirm.assert_not_awaited()


def test_update_receipt_route_delegates_payload_and_returns_receipt(
    receipt_client, service, receipt, user, update_payload
):
    service.update_receipt.return_value = receipt

    response = receipt_client.put(
        f"/receipts/{receipt.id}", json=update_payload.model_dump(mode="json")
    )

    assert response.status_code == 200
    assert response.json() == receipt.model_dump(mode="json")
    service.update_receipt.assert_awaited_once_with(
        receipt_id=receipt.id, user=user, payload=update_payload
    )


@pytest.mark.parametrize("status", [404, 409, 500])
def test_update_receipt_route_preserves_service_errors(
    receipt_client, service, update_payload, status
):
    service.update_receipt.side_effect = HTTPException(status, "Update failed")

    response = receipt_client.put(
        f"/receipts/{uuid4()}", json=update_payload.model_dump(mode="json")
    )

    assert response.status_code == status
    assert response.json() == {"detail": "Update failed"}


@pytest.mark.parametrize("invalid", ["id", "payload"])
def test_update_receipt_route_rejects_invalid_input(
    receipt_client, service, update_payload, invalid
):
    receipt_id = "not-a-uuid" if invalid == "id" else str(uuid4())
    payload = {} if invalid == "payload" else update_payload.model_dump(mode="json")

    response = receipt_client.put(f"/receipts/{receipt_id}", json=payload)

    assert response.status_code == 422
    service.update_receipt.assert_not_awaited()


def test_update_receipt_route_requires_authentication(service, update_payload):
    app = FastAPI()
    app.include_router(router, prefix="/receipts")
    app.dependency_overrides[receipt_service] = lambda: service

    with TestClient(app) as client:
        response = client.put(
            f"/receipts/{uuid4()}", json=update_payload.model_dump(mode="json")
        )

    assert response.status_code in (401, 403)
    service.update_receipt.assert_not_awaited()


def test_update_receipt_route_rejects_response_that_is_not_a_receipt(
    receipt_client, service, update_payload
):
    service.update_receipt.return_value = Message(
        message="Receipt updated successfully"
    )

    with pytest.raises(ResponseValidationError):
        receipt_client.put(
            f"/receipts/{uuid4()}", json=update_payload.model_dump(mode="json")
        )


def test_update_receipt_route_rejects_blank_required_text(
    receipt_client, service, update_payload
):
    payload = {**update_payload.model_dump(mode="json"), "beneficiary": "   "}

    response = receipt_client.put(f"/receipts/{uuid4()}", json=payload)

    assert response.status_code == 422
    service.update_receipt.assert_not_awaited()


def test_update_receipt_route_accepts_and_strips_category(
    receipt_client, service, receipt, update_payload
):
    service.update_receipt.return_value = receipt
    payload = {
        **update_payload.model_dump(mode="json"),
        "category": "  Utilities  ",
    }

    response = receipt_client.put(f"/receipts/{receipt.id}", json=payload)

    assert response.status_code == 200
    sent = service.update_receipt.await_args.kwargs["payload"]
    assert sent.category == "  Utilities  "


def test_confirm_route_documents_the_envelope_and_the_409_body():
    app = FastAPI()
    app.include_router(router, prefix="/receipts")

    schema = app.openapi()["paths"]["/receipts/{receipt_id}/confirm"]["post"]

    success = schema["responses"]["200"]["content"]["application/json"]["schema"]
    assert success["$ref"].endswith("/ReceiptConfirmResultSchema")
    conflict = schema["responses"]["409"]["content"]["application/json"]["schema"]
    assert conflict["$ref"].endswith("/ReceiptConfirmConflictSchema")
    properties = app.openapi()["components"]["schemas"]["ReceiptConfirmResultSchema"][
        "properties"
    ]
    assert set(properties) == {"payment", "transaction", "series", "occurrence"}
    assert properties["transaction"]["anyOf"][1]["type"] == "null"
