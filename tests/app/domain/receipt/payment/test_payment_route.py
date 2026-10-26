from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from fastapi_pagination import LimitOffsetParams

from app.core.pagination import CustomLimitOffsetPage
from app.core.security import get_current_user
from app.domain.receipt.payment.route import payment_service, router
from app.domain.receipt.payment.schema import (
    PaymentSchema,
    PaymentDashboardResponseSchema,
    PaymentDashboardRequestSchema,
)
from app.domain.receipt.payment.service import PaymentService


@pytest.fixture
def route_service():
    return AsyncMock(spec=PaymentService)


@pytest.fixture
def payment_app(route_service):
    app = FastAPI()
    app.include_router(router, prefix="/receipts/payments")
    app.dependency_overrides[payment_service] = lambda: route_service
    return app


@pytest.fixture
def payment_client(payment_app, user):
    payment_app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(payment_app) as client:
        yield client


def test_dependency_binds_session():
    session = AsyncMock()

    service = payment_service(session)

    assert isinstance(service, PaymentService)
    assert service.repository.session is session


@pytest.mark.parametrize(
    ("query", "page", "limit", "offset", "paginated"),
    [
        ("", None, 12, 0, True),
        ("?page=2&limit=2", 2, 2, 0, True),
        ("?limit=2&offset=4", None, 2, 4, True),
        ("", None, 12, 0, False),
    ],
)
def test_list_all_serializes_results_and_delegates_filters(
    payment_client,
    route_service,
    payment_output,
    user,
    query,
    page,
    limit,
    offset,
    paginated,
):
    expected = PaymentSchema.model_validate(payment_output)
    actual_offset = (page - 1) * limit if page is not None else offset
    result = (
        CustomLimitOffsetPage.create(
            [expected],
            total=8,
            params=LimitOffsetParams(limit=limit, offset=actual_offset),
        )
        if paginated
        else [payment_output]
    )
    route_service.list_all.return_value = result

    response = payment_client.get(f"/receipts/payments{query}")

    assert response.status_code == 200
    if paginated:
        assert response.json() == result.model_dump(mode="json")
    else:
        assert response.json() == [expected.model_dump(mode="json")]
    route_service.list_all.assert_awaited_once()
    kwargs = route_service.list_all.await_args.kwargs
    assert kwargs["user"] is user
    assert kwargs["page_filter"].page == page
    assert kwargs["page_filter"].limit == limit
    assert kwargs["page_filter"].offset == offset


def test_find_one_returns_nested_payment(
    payment_client, route_service, payment_output, user
):
    route_service.find_one.return_value = payment_output

    response = payment_client.get(f"/receipts/payments/{payment_output.id}")

    assert response.status_code == 200
    assert response.json() == PaymentSchema.model_validate(payment_output).model_dump(
        mode="json"
    )
    route_service.find_one.assert_awaited_once_with(
        payment_id=payment_output.id, user=user
    )


@pytest.mark.parametrize(
    ("path", "method", "status", "detail"),
    [
        ("", "list_all", 500, "Internal server error"),
        (f"/{uuid4()}", "find_one", 404, "Payment not found"),
    ],
)
def test_routes_preserve_service_errors(
    payment_client, route_service, path, method, status, detail
):
    getattr(route_service, method).side_effect = HTTPException(status, detail)

    response = payment_client.get(f"/receipts/payments{path}")

    assert response.status_code == status
    assert response.json() == {"detail": detail}


@pytest.mark.parametrize(
    "suffix",
    ["?page=0", "?limit=0", "?offset=-1", "?page=invalid", "/not-a-uuid"],
)
def test_routes_reject_invalid_parameters(payment_client, route_service, suffix):
    response = payment_client.get(f"/receipts/payments{suffix}")

    assert response.status_code == 422
    route_service.list_all.assert_not_awaited()
    route_service.find_one.assert_not_awaited()


@pytest.mark.parametrize(
    "suffix",
    ["", f"/{uuid4()}", "/dashboard?start_date=2026-01-01&end_date=2026-12-31"],
)
def test_routes_require_authentication(payment_app, route_service, suffix):
    with TestClient(payment_app) as client:
        response = client.get(f"/receipts/payments{suffix}")

    assert response.status_code in (401, 403)
    route_service.list_all.assert_not_awaited()
    route_service.find_one.assert_not_awaited()
    route_service.get_dashboard.assert_not_awaited()


@pytest.mark.parametrize("filtered", [False, True])
def test_dashboard_route_validates_query_and_returns_response(
    payment_client, route_service, user, dashboard_params, dashboard_response, filtered
):
    if not filtered:
        dashboard_params = PaymentDashboardRequestSchema(
            start_date=dashboard_params.start_date, end_date=dashboard_params.end_date
        )
    expected = PaymentDashboardResponseSchema.model_validate(dashboard_response)
    route_service.get_dashboard.return_value = expected

    response = payment_client.get(
        "/receipts/payments/dashboard",
        params=dashboard_params.model_dump(mode="json", exclude_none=True),
    )

    assert response.status_code == 200
    assert response.json() == expected.model_dump(mode="json")
    route_service.get_dashboard.assert_awaited_once_with(
        params=dashboard_params, user=user
    )
    route_service.find_one.assert_not_awaited()


@pytest.mark.parametrize(
    "invalid",
    [
        {},
        {"start_date": "invalid", "end_date": "2026-12-31"},
        {"start_date": "2026-01-01", "end_date": "invalid"},
        *[
            {"start_date": "2026-01-01", "end_date": "2026-12-31", key: "invalid"}
            for key in ("payer_id", "subcategory_id", "beneficiary_id")
        ],
    ],
)
def test_dashboard_route_rejects_invalid_query(payment_client, route_service, invalid):
    response = payment_client.get("/receipts/payments/dashboard", params=invalid)

    assert response.status_code == 422
    route_service.get_dashboard.assert_not_awaited()


def test_dashboard_route_preserves_service_error(
    payment_client, route_service, dashboard_params
):
    route_service.get_dashboard.side_effect = HTTPException(503, "Service unavailable")

    response = payment_client.get(
        "/receipts/payments/dashboard",
        params=dashboard_params.model_dump(mode="json", exclude_none=True),
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Service unavailable"}
