from io import BytesIO
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, UploadFile
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
from app.domain.receipt.schema import ReceiptSchema
from app.domain.receipt.service import ReceiptService
from app.models import ReceiptStatusEnum, utcnow


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
        ("", 12, 0, None),
        ("?limit=2&offset=4", 2, 4, None),
        ("?page=2&limit=2", 2, 0, 2),
    ],
)
def test_list_all_returns_paginated_receipts(
    receipt_client, service, receipt, user, query, limit, offset, page
):
    result_offset = (page - 1) * limit if page is not None else offset
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
        "/receipts?limit=0",
        "/receipts?offset=-1",
        "/receipts?page=0",
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
