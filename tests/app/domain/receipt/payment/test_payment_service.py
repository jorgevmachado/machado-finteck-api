from http import HTTPStatus
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi_pagination import LimitOffsetParams

from app.core.exceptions import handle_service_exception
from app.core.pagination import CustomLimitOffsetPage
from app.domain.receipt.payment.repository import PaymentRepository
from app.domain.receipt.payment.schema import (
    PaymentDashboardRequestSchema,
    PaymentDashboardResponseSchema,
)
from app.domain.receipt.payment.service import PaymentService
from app.models import Payment
from app.shared.schemas import FilterPage

MODULE = "app.domain.receipt.payment.service"
pytestmark = pytest.mark.asyncio


async def test_from_session_binds_repository():
    session = AsyncMock()

    service = PaymentService.from_session(session)

    assert isinstance(service.repository, PaymentRepository)
    assert service.repository.session is session


@pytest.mark.parametrize("paginated", [False, True])
async def test_list_all_passes_owner_separately_without_mutating_filter(
    payment_service, payment_repository, payment, user, paginated
):
    page_filter = FilterPage.build(limit=2, offset=0, user_id=uuid4())
    expected = (
        CustomLimitOffsetPage.create(
            [payment], total=1, params=LimitOffsetParams(limit=2, offset=0)
        )
        if paginated
        else [payment]
    )
    payment_repository.list.return_value = expected

    result = await payment_service.list_all(page_filter, user)

    assert result is expected
    payment_repository.list.assert_awaited_once_with(
        user_id=user.id, page_filter=page_filter
    )
    assert page_filter.user_id != user.id


async def test_find_one_returns_owner_scoped_payment(
    payment_service, payment_repository, payment, user
):
    payment_repository.find_by.return_value = payment

    with patch(f"{MODULE}.log_service_success") as success:
        result = await payment_service.find_one(payment.id, user)

    assert result is payment
    payment_repository.find_by.assert_awaited_once_with(id=payment.id, user_id=user.id)
    assert success.call_args.kwargs["operation"] == "find_one"
    assert success.call_args.kwargs["user_request"] == user.username
    assert str(payment.id) in success.call_args.kwargs["message"]


async def test_find_one_missing_or_inaccessible_returns_404(
    payment_service, payment_repository, user
):
    payment_id = uuid4()
    with pytest.raises(HTTPException) as caught:
        await payment_service.find_one(payment_id, user)

    assert caught.value.status_code == HTTPStatus.NOT_FOUND
    assert caught.value.detail == "Payment not found"
    payment_repository.find_by.assert_awaited_once_with(id=payment_id, user_id=user.id)


@pytest.mark.parametrize("found", [False, True])
async def test_find_by_receipt_preserves_optional_result_and_owner(
    payment_service, payment_repository, payment, user, found
):
    expected = payment if found else None
    payment_repository.find_by.return_value = expected

    result = await payment_service.find_by(user, payment.receipt_id)

    assert result is expected
    payment_repository.find_by.assert_awaited_once_with(
        receipt_id=payment.receipt_id, user_id=user.id
    )


@pytest.mark.parametrize("exists", [False, True])
async def test_check_receipt_rejects_existing_payment(
    payment_service, payment_repository, payment, user, exists
):
    payment_repository.find_by.return_value = payment if exists else None
    if exists:
        with pytest.raises(HTTPException) as caught:
            await payment_service.check_receipt(payment.receipt_id, user)
        assert caught.value.status_code == HTTPStatus.CONFLICT
        assert caught.value.detail == "Receipt already has a payment"
    else:
        assert await payment_service.check_receipt(payment.receipt_id, user) is None

    payment_repository.find_by.assert_awaited_once_with(
        receipt_id=payment.receipt_id, user_id=user.id
    )
    payment_repository.save.assert_not_awaited()


@pytest.mark.parametrize("optional_fields", [False, True])
async def test_create_persists_all_fields_and_returns_saved_payment(
    payment_service, payment_repository, payment_values, payment, user, optional_fields
):
    if not optional_fields:
        payment_values.update(description=None, destination_institution_id=None)
    payment_repository.save.side_effect = None
    payment_repository.save.return_value = payment

    result = await payment_service.create(user=user, **payment_values)

    assert result is payment
    payment_repository.save.assert_awaited_once()
    entity = payment_repository.save.await_args.kwargs["entity"]
    assert isinstance(entity, Payment)
    assert entity.user_id == user.id
    for name, value in payment_values.items():
        assert getattr(entity, name) == value


@pytest.mark.parametrize(
    ("operation", "repository_method"),
    [
        ("list_all", "list"),
        ("find_one", "find_by"),
        ("find_by", "find_by"),
        ("check_receipt", "find_by"),
        ("create", "save"),
    ],
)
async def test_repository_failures_are_logged_and_propagated(
    payment_service,
    payment_repository,
    payment_values,
    user,
    operation,
    repository_method,
):
    exception = RuntimeError("database failure")
    getattr(payment_repository, repository_method).side_effect = exception
    arguments = {
        "list_all": {"page_filter": FilterPage(limit=12, offset=0)},
        "find_one": {"payment_id": uuid4()},
        "find_by": {"receipt_id": uuid4()},
        "check_receipt": {"receipt_id": uuid4()},
        "create": payment_values,
    }
    with (
        patch(f"{MODULE}.log_service_success") as success,
        patch(
            f"{MODULE}.handle_service_exception", wraps=handle_service_exception
        ) as error,
        pytest.raises(HTTPException) as caught,
    ):
        await getattr(payment_service, operation)(user=user, **arguments[operation])

    assert caught.value.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    success.assert_not_called()
    error.assert_called_once()
    assert error.call_args.args[0] is exception
    assert error.call_args.kwargs["operation"] == operation
    assert error.call_args.kwargs["user_request"] == user.username


@pytest.mark.parametrize("filtered", [False, True])
@pytest.mark.parametrize("empty", [False, True])
async def test_dashboard_scopes_queries_and_builds_response(
    payment_service,
    payment_repository,
    user,
    dashboard_params,
    dashboard_data,
    dashboard_response,
    filtered,
    empty,
):
    if not filtered:
        dashboard_params = PaymentDashboardRequestSchema(
            start_date=dashboard_params.start_date, end_date=dashboard_params.end_date
        )
    if empty:
        dashboard_data["summary"] = {"total": 0, "count": 0, "average": 0, "highest": 0}
        dashboard_response["summary"] = dashboard_data["summary"]
        for key in (
            "monthly",
            "institutions",
            "beneficiaries",
            "subcategories",
            "payers",
        ):
            dashboard_data[key] = []
            dashboard_response[key] = []
    for key, value in dashboard_data.items():
        getattr(payment_repository, f"dashboard_{key}").return_value = value

    result = await payment_service.get_dashboard(dashboard_params, user)

    assert isinstance(result, PaymentDashboardResponseSchema)
    assert result == PaymentDashboardResponseSchema.model_validate(dashboard_response)
    common = {
        "user_id": user.id,
        "start_date": dashboard_params.start_date,
        "end_date": dashboard_params.end_date,
        "institution": dashboard_params.institution,
    }
    for key in ("summary", "monthly", "institutions", "beneficiaries"):
        getattr(payment_repository, f"dashboard_{key}").assert_awaited_once_with(
            **common, beneficiary_id=dashboard_params.beneficiary_id
        )
    payment_repository.dashboard_payers.assert_awaited_once_with(
        **common, payer_id=dashboard_params.payer_id
    )
    payment_repository.dashboard_subcategories.assert_awaited_once_with(
        **common, subcategory_id=dashboard_params.subcategory_id
    )


@pytest.mark.parametrize(
    "failed_method",
    ["summary", "monthly", "institutions", "beneficiaries", "payers", "subcategories"],
)
async def test_dashboard_propagates_repository_errors_and_stops_remaining_queries(
    payment_service,
    payment_repository,
    user,
    dashboard_params,
    failed_method,
):
    methods = [
        "summary",
        "monthly",
        "institutions",
        "beneficiaries",
        "payers",
        "subcategories",
    ]
    exception = RuntimeError("database failure")
    getattr(payment_repository, f"dashboard_{failed_method}").side_effect = exception

    with pytest.raises(RuntimeError) as caught:
        await payment_service.get_dashboard(dashboard_params, user)

    assert caught.value is exception
    for method in methods[methods.index(failed_method) + 1 :]:
        getattr(payment_repository, f"dashboard_{method}").assert_not_awaited()
