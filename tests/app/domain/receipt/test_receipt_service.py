from datetime import date
from decimal import Decimal
from io import BytesIO
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile
from fastapi_pagination import LimitOffsetParams
from starlette.datastructures import Headers

from app.core.exceptions import handle_service_exception
from app.core.pagination import CustomLimitOffsetPage
from app.domain.receipt.data.enums import DataStatusEnum
from app.domain.receipt.data.schema import ReceiptData, ReceiptDataError
from app.domain.receipt.file.file import MAX_BATCH_FILES
from app.domain.receipt.interpretation.schema import InterpretationResult
from app.domain.receipt.repository import ReceiptRepository
from app.domain.receipt.rules.schema import ReceiptRulesFilter, ReceiptRulesSchema
from app.domain.receipt.schema import ReceiptUploadSchema
from app.domain.receipt.service import ReceiptService
from app.models import (
    Receipt,
    ReceiptIdentificationRule,
    ReceiptInterpretationProfile,
    ReceiptStatusEnum,
)
from app.shared.schemas import FilterPage

MODULE = "app.domain.receipt.service"
pytestmark = pytest.mark.asyncio


@pytest.fixture
def service():
    repository = MagicMock(spec=ReceiptRepository)
    repository.session = MagicMock()
    repository.find_by.return_value = None
    repository.save.side_effect = lambda *, entity, user_id: entity

    @asynccontextmanager
    async def transaction():
        yield

    repository.transaction = transaction
    return ReceiptService(repository)


@pytest.fixture
def receipt(user):
    return Receipt(
        user_id=user.id,
        file_name="receipt.pdf",
        file_type="application/pdf",
        file_size=7,
        file_hash="file-hash",
        status=ReceiptStatusEnum.RECEIVED,
        data=None,
    )


@pytest.mark.parametrize("source", ["Nubank", None])
async def test_upload_interprets_extracted_text_with_active_user_rules(
    user, source, service
):
    service.extraction_service = AsyncMock()
    service.extraction_service.extract.return_value = "receipt text"
    service.rules_service = AsyncMock()
    profile = ReceiptInterpretationProfile(
        user_id=user.id, name="Bank", institution_code="BANK"
    )
    profile.identification_rules.extend(
        [
            ReceiptIdentificationRule(profile_id=profile.id, pattern="bank", weight=1),
            ReceiptIdentificationRule(
                profile_id=profile.id, pattern="inactive", weight=1, is_active=False
            ),
        ]
    )
    rules = [ReceiptRulesSchema.model_validate(profile)]
    default = ReceiptInterpretationProfile(
        user_id=None, name="Default", institution_code=None
    )
    rules.append(ReceiptRulesSchema.model_validate(default))
    service.rules_service.list_profiles.return_value = rules
    file = UploadFile(
        file=BytesIO(b"content"),
        filename="receipt.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )
    with (
        patch(f"{MODULE}.validate_file", return_value=b"content"),
        patch(f"{MODULE}.Interpretation") as interpretation,
    ):
        fields = {
            name: {"value": None, "status": DataStatusEnum.NOT_FOUND}
            for name in ReceiptData.model_fields
        }
        if source is not None:
            fields["source_institution"] = {
                "value": source,
                "status": DataStatusEnum.FOUND,
            }
        expected = InterpretationResult(
            data=ReceiptData.model_validate(fields),
            errors=[
                ReceiptDataError(field="paid_amount", status=DataStatusEnum.NOT_FOUND)
            ],
        )
        interpretation.return_value.result.return_value = expected
        result = await service.upload(file, user)

    service.rules_service.list_profiles.assert_awaited_once_with(
        ReceiptRulesFilter(is_active=True, limit=None), user
    )
    interpretation.assert_called_once_with(rules, "receipt text")
    assert rules[1].scope == "system"
    assert [rule.pattern for rule in rules[0].identification_rules] == ["bank"]
    interpretation.return_value.result.assert_called_once_with()
    assert result.data == expected.data
    assert result.errors == expected.errors
    assert result.file_name == "receipt.pdf"
    assert result.status == ReceiptStatusEnum.FAILED
    entity = service.repository.save.call_args.kwargs["entity"]
    assert entity.user_id == user.id
    assert entity.file_hash
    assert entity.data == expected.data.model_dump(mode="json")
    assert result.id == entity.id


async def test_upload_does_not_report_success_when_loading_rules_fails(user, service):
    service.extraction_service = AsyncMock()
    service.extraction_service.extract.return_value = "receipt text"
    service.rules_service = AsyncMock()
    service.rules_service.list_profiles.side_effect = RuntimeError("database failure")
    with (
        patch(f"{MODULE}.validate_file", return_value=b"content"),
        patch.object(service, "find_by_hash", return_value=None),
        patch("app.core.service.base.log_service_success") as success,
        pytest.raises(HTTPException) as caught,
    ):
        await service.upload(
            UploadFile(file=BytesIO(b"content"), filename="receipt.pdf"), user
        )
    assert caught.value.status_code == 500
    success.assert_not_called()


async def test_find_by_uses_owner_context_for_operation_logging(user, service):
    with patch("app.core.service.base.log_service_success") as success:
        result = await service.find_by_hash(user, "file-hash")
    assert result is None
    assert success.call_args.kwargs["user_request"] == user.username
    assert success.call_args.kwargs["operation"] == "find_by"
    service.repository.find_by.assert_awaited_once_with(
        filters={"file_hash": "file-hash"}, user_id=user.id
    )


@pytest.mark.parametrize("paginated", [True, False])
async def test_list_all_scopes_results_to_owner(user, service, receipt, paginated):
    page_filter = FilterPage(limit=2, offset=0)
    expected = (
        CustomLimitOffsetPage.create(
            [receipt], total=1, params=LimitOffsetParams(limit=2, offset=0)
        )
        if paginated
        else [receipt]
    )
    service.repository.list_all.return_value = expected

    with patch("app.core.service.base.log_service_success") as success:
        result = await service.list_all(page_filter, user)

    assert result is expected
    scoped_filter = service.repository.list_all.call_args.kwargs["page_filter"]
    assert service.repository.list_all.call_args.kwargs["user_id"] == user.id
    assert scoped_filter is page_filter
    assert scoped_filter.limit == 2
    assert scoped_filter.offset == 0
    assert success.call_args.kwargs["user_request"] == user.username


async def test_find_one_scopes_lookup_to_owner(user, service, receipt):
    service.repository.find_by.return_value = receipt

    assert await service.find_one(receipt.id, user) is receipt

    service.repository.find_by.assert_awaited_once_with(
        filters={"id": receipt.id}, user_id=user.id
    )


async def test_find_one_not_found_returns_404(user, service):
    with pytest.raises(HTTPException) as caught:
        await service.find_one(uuid4(), user)

    assert caught.value.status_code == 404
    assert caught.value.detail == "Receipt not found"


async def test_persist_upload_logs_only_after_transaction_commits(user, service):
    committed = False

    @asynccontextmanager
    async def transaction():
        nonlocal committed
        yield
        committed = True

    service.repository.transaction = transaction
    interpretation = InterpretationResult(
        data=ReceiptData.model_validate(
            {
                name: {"value": None, "status": DataStatusEnum.NOT_FOUND}
                for name in ReceiptData.model_fields
            }
        ),
        errors=[],
    )
    with patch("app.core.service.base.log_service_success") as success:
        success.side_effect = lambda *args, **kwargs: (
            None if committed else pytest.fail("Success before commit")
        )
        result = await service.persist_upload(
            user=user,
            file_size=7,
            file_hash="hash",
            interpretation=interpretation,
            file_name="receipt.pdf",
            content_type="application/pdf",
        )
    assert result.status == ReceiptStatusEnum.RECEIVED
    assert result.user_id == user.id
    success.assert_called_once()


async def test_confirmation_commit_failure_never_reports_success(
    confirmation_service, receipt, user, confirm_payload
):
    @asynccontextmanager
    async def transaction():
        yield
        raise RuntimeError("commit failed")

    confirmation_service.repository.transaction = transaction
    with patch("app.core.service.base.log_service_success") as success:
        with pytest.raises(HTTPException) as caught:
            await confirmation_service.confirm(receipt.id, user, confirm_payload)
    assert caught.value.status_code == 500
    assert str(caught.value.__cause__) == "commit failed"
    assert all(
        entry.kwargs["operation"] != "confirm" for entry in success.call_args_list
    )


@pytest.mark.parametrize("operation", ["list_all", "find_one"])
async def test_read_failure_is_logged_and_propagated(user, service, operation):
    repository_method = (
        service.repository.list_all
        if operation == "list_all"
        else service.repository.find_by
    )
    repository_method.side_effect = RuntimeError("database failure")
    with (
        patch("app.core.service.base.log_service_success") as success,
        patch(
            "app.core.service.base.handle_service_exception",
            wraps=handle_service_exception,
        ) as error,
        pytest.raises(HTTPException) as caught,
    ):
        if operation == "list_all":
            await service.list_all(FilterPage(limit=12, offset=0), user)
        else:
            await service.find_one(uuid4(), user)

    assert caught.value.status_code == 500
    success.assert_not_called()
    assert error.call_args.kwargs["operation"] == operation
    assert error.call_args.kwargs["user_request"] == user.username


@pytest.mark.parametrize(
    "status", [ReceiptStatusEnum.RECEIVED, ReceiptStatusEnum.PROCESSED]
)
async def test_upload_duplicate_does_not_extract_or_save(
    user, service, receipt, status
):
    receipt.status = status
    service.repository.find_by.return_value = receipt
    service.extraction_service = AsyncMock()
    with patch(f"{MODULE}.validate_file", return_value=b"content"):
        result = await service.upload(
            UploadFile(file=BytesIO(b"content"), filename="receipt.pdf"), user
        )

    assert result.id == receipt.id
    assert result.status == ReceiptStatusEnum.FAILED
    assert result.error_message == "Receipt has already been received or processed"
    service.extraction_service.extract.assert_not_awaited()
    service.repository.save.assert_not_awaited()


@pytest.mark.parametrize("replace_metadata", [True, False])
async def test_upload_retries_failed_receipt_and_preserves_identity(
    user, service, receipt, replace_metadata
):
    receipt.status = ReceiptStatusEnum.FAILED
    original_id = receipt.id
    original_hash = receipt.file_hash
    original_name = receipt.file_name
    original_type = receipt.file_type
    service.repository.find_by.return_value = receipt
    service.extraction_service = AsyncMock()
    service.extraction_service.extract.return_value = "retry text"
    interpretation = InterpretationResult(
        data=ReceiptData.model_validate(
            {
                name: {"value": None, "status": DataStatusEnum.NOT_FOUND}
                for name in ReceiptData.model_fields
            }
        ),
        errors=(
            []
            if replace_metadata
            else [
                ReceiptDataError(field="paid_amount", status=DataStatusEnum.NOT_FOUND)
            ]
        ),
    )
    service._interpret_receipt = AsyncMock(return_value=interpretation)
    file = UploadFile(
        file=BytesIO(b"retry content"),
        filename="retry.png" if replace_metadata else None,
        headers=Headers({"content-type": "image/png"}) if replace_metadata else None,
    )

    with patch(f"{MODULE}.validate_file", return_value=b"retry content"):
        result = await service.upload(file, user)

    service.repository.save.assert_awaited_once_with(entity=receipt, user_id=user.id)
    service.extraction_service.extract.assert_awaited_once_with(
        content=b"retry content", content_type=file.content_type
    )
    service._interpret_receipt.assert_awaited_once_with("retry text", user)
    assert receipt.id == result.id == original_id
    assert receipt.file_hash == original_hash
    assert receipt.user_id == user.id
    assert (
        receipt.file_name
        == result.file_name
        == ("retry.png" if replace_metadata else original_name)
    )
    assert (
        receipt.file_type
        == result.file_type
        == ("image/png" if replace_metadata else original_type)
    )
    assert receipt.file_size == result.file_size == len(b"retry content")
    assert receipt.data == interpretation.data.model_dump(mode="json")
    assert result.data == interpretation.data
    assert result.errors == interpretation.errors
    assert (
        receipt.status
        == result.status
        == (
            ReceiptStatusEnum.RECEIVED if replace_metadata else ReceiptStatusEnum.FAILED
        )
    )
    assert result.error_message is None


async def test_batch_rejects_excess_files_before_uploading(user, service):
    service.upload = AsyncMock()
    files = [
        UploadFile(file=BytesIO(b"content"), filename="receipt.pdf")
        for _ in range(MAX_BATCH_FILES + 1)
    ]

    with pytest.raises(HTTPException) as caught:
        await service.batch(files, user)

    assert caught.value.status_code == 400
    assert caught.value.detail == (
        f"A maximum of {MAX_BATCH_FILES} files can be uploaded at once."
    )
    service.upload.assert_not_awaited()


@pytest.mark.parametrize("status", list(ReceiptStatusEnum))
async def test_validate_confirm_receipt_requires_received_status(
    service, receipt, user, status
):
    receipt.status = status
    service.repository.find_by.return_value = receipt

    if status == ReceiptStatusEnum.RECEIVED:
        assert await service.validate_confirm_receipt(receipt.id, user) is receipt
    else:
        with pytest.raises(HTTPException) as caught:
            await service.validate_confirm_receipt(receipt.id, user)
        assert caught.value.status_code == 409
        assert caught.value.detail == "Receipt is not ready for confirmation"

    service.repository.find_by.assert_awaited_once_with(
        filters={"id": receipt.id}, user_id=user.id
    )
    service.repository.save.assert_not_awaited()


@pytest.fixture
def confirmation_service(service, receipt):
    service.repository.find_by.return_value = receipt
    service.payment_service = AsyncMock()
    service.payment_service.add_owned.side_effect = lambda user, payload: (
        SimpleNamespace(id=uuid4(), **payload.model_dump())
    )
    for name in ("payer_service", "beneficiary_service", "institution_service"):
        dependency = AsyncMock()
        dependency.resolve.return_value = SimpleNamespace(id=uuid4())
        setattr(service, name, dependency)
    service.category_service = AsyncMock()
    service.category_service.find_subcategory_by_id.return_value = SimpleNamespace(
        id=uuid4()
    )
    service.transaction_service = AsyncMock()
    service.transaction_service.add_owned.side_effect = lambda user, payload: (
        SimpleNamespace(id=uuid4(), **payload.model_dump())
    )
    service.series_service = AsyncMock()
    service.series_service.resolve_open_series.return_value = None
    service.series_service.add_owned.side_effect = lambda user, payload: (
        SimpleNamespace(id=uuid4(), **payload.model_dump())
    )
    service.scheduled_service = AsyncMock()
    service.scheduled_service.find_by.return_value = None
    service.scheduled_service.add_owned.side_effect = lambda user, payload: (
        SimpleNamespace(id=uuid4(), **payload.model_dump())
    )
    return service


async def test_confirm_simple_writes_payment_and_transaction_in_one_transaction(
    confirmation_service, receipt, user, confirm_payload
):
    service = confirmation_service
    service.payment_service.check_receipt.assert_awaited if False else None
    events = []
    original_save = service.repository.save

    service.repository.save = AsyncMock(
        side_effect=lambda **kwargs: events.append("receipt") or kwargs["entity"]
    )
    service.transaction_service.add_owned.side_effect = lambda user, payload: (
        events.append("transaction")
        or SimpleNamespace(id=uuid4(), **payload.model_dump())
    )
    service.payment_service.add_owned.side_effect = lambda user, payload: (
        events.append("payment") or SimpleNamespace(id=uuid4(), **payload.model_dump())
    )

    result = await service.confirm(receipt.id, user, confirm_payload)

    assert events == ["payment", "transaction", "receipt"]
    assert receipt.status == ReceiptStatusEnum.PROCESSED
    assert result.transaction is not None
    assert result.series is None and result.occurrence is None
    transaction_payload = service.transaction_service.add_owned.await_args.args[1]
    assert transaction_payload.receipt_payment_id == result.payment.id
    assert transaction_payload.status == "SETTLED"
    assert transaction_payload.settled_on == confirm_payload.payment_date
    assert original_save is not None


@pytest.mark.parametrize("has_destination", [False, True])
async def test_confirm_resolves_receipt_entities_before_writing(
    confirmation_service, receipt, user, confirm_payload, has_destination
):
    service = confirmation_service
    if not has_destination:
        confirm_payload.destination_institution = None
        confirm_payload.description = None
    source = SimpleNamespace(id=uuid4())
    destination = SimpleNamespace(id=uuid4())
    service.institution_service.resolve.side_effect = [source, destination]

    await service.confirm(receipt.id, user, confirm_payload)

    service.payment_service.check_receipt.assert_awaited_once_with(receipt.id, user)
    service.payer_service.resolve.assert_awaited_once_with(
        user=user, name=confirm_payload.payer
    )
    service.beneficiary_service.resolve.assert_awaited_once_with(
        user=user, name=confirm_payload.beneficiary
    )
    service.category_service.find_subcategory_by_id.assert_awaited_once_with(
        subcategory_id=confirm_payload.subcategory_id, user_id=user.id
    )
    assert service.institution_service.resolve.await_args_list == [
        call(user=user, name=confirm_payload.source_institution),
        *(
            [call(user=user, name=confirm_payload.destination_institution)]
            if has_destination
            else []
        ),
    ]
    payment_payload = service.payment_service.add_owned.await_args.args[1]
    assert payment_payload.payer_id == service.payer_service.resolve.return_value.id
    assert payment_payload.receipt_id == receipt.id
    assert payment_payload.amount == confirm_payload.paid_amount
    assert payment_payload.destination_institution_id == (
        destination.id if has_destination else None
    )


async def test_confirm_recurring_reuses_the_open_series_and_writes_an_occurrence(
    confirmation_service, receipt, user, confirm_payload
):
    service = confirmation_service
    confirm_payload.transaction_kind = "RECURRING"
    confirm_payload.frequency_unit = "MONTH"
    confirm_payload.frequency_interval = 1
    existing_series = SimpleNamespace(
        id=uuid4(),
        name=confirm_payload.name,
        start_date=date(2026, 8, 26),
        frequency_unit="MONTH",
        frequency_interval=1,
        week_day=None,
        day_of_month=26,
        month=None,
        installments=None,
        kind="OPEN",
    )
    service.series_service.resolve_open_series.return_value = existing_series

    result = await service.confirm(receipt.id, user, confirm_payload)

    service.series_service.resolve_open_series.assert_awaited_once_with(
        user=user,
        name=confirm_payload.name,
        account_id=confirm_payload.account_id,
        direction=confirm_payload.direction,
    )
    service.series_service.add_owned.assert_not_awaited()
    occurrence_payload = service.scheduled_service.add_owned.await_args.args[1]
    assert occurrence_payload.transaction_series_id == existing_series.id
    # Series starts 2026-08-26 and the payment is 2026-10-26: the paid month is
    # the third occurrence, not the first.
    assert occurrence_payload.occurrence_index == 3
    assert occurrence_payload.status == "SETTLED"
    assert occurrence_payload.receipt_payment_id == result.payment.id
    assert result.series is not None and result.occurrence is not None
    assert result.transaction is None


async def test_confirm_recurring_creates_the_series_when_none_matches(
    confirmation_service, receipt, user, confirm_payload
):
    service = confirmation_service
    confirm_payload.transaction_kind = "RECURRING"
    confirm_payload.frequency_unit = "MONTH"
    confirm_payload.frequency_interval = 1

    await service.confirm(receipt.id, user, confirm_payload)

    series_payload = service.series_service.add_owned.await_args.args[1]
    assert series_payload.kind == "OPEN"
    assert series_payload.start_date == confirm_payload.payment_date
    assert series_payload.frequency_unit == "MONTH"


async def test_confirm_installment_derives_start_date_from_the_position(
    confirmation_service, receipt, user, confirm_payload
):
    service = confirmation_service
    confirm_payload.transaction_kind = "INSTALLMENT"
    confirm_payload.installment_index = 3
    confirm_payload.installments_total = 10
    confirm_payload.payment_date = date(2025, 11, 13)

    await service.confirm(receipt.id, user, confirm_payload)

    series_payload = service.series_service.add_owned.await_args.args[1]
    assert series_payload.kind == "CLOSED"
    assert series_payload.installments == 10
    assert series_payload.start_date == date(2025, 9, 13)
    occurrence_payload = service.scheduled_service.add_owned.await_args.args[1]
    assert occurrence_payload.occurrence_index == 3
    assert occurrence_payload.occurrence_on == date(2025, 11, 13)


async def test_confirm_refuses_a_settled_occurrence_without_consent(
    confirmation_service, receipt, user, confirm_payload
):
    service = confirmation_service
    confirm_payload.transaction_kind = "RECURRING"
    confirm_payload.frequency_unit = "MONTH"
    confirm_payload.frequency_interval = 1
    service.scheduled_service.find_by.return_value = SimpleNamespace(
        id=uuid4(), settled_on=date(2025, 11, 13), value=Decimal("55.90")
    )

    with pytest.raises(HTTPException) as caught:
        await service.confirm(receipt.id, user, confirm_payload)

    assert caught.value.status_code == 409
    assert caught.value.detail["type"] == "OCCURRENCE_EXISTS"
    assert caught.value.detail["existing"]["value"] == "55.90"
    service.scheduled_service.add_owned.assert_not_awaited()
    service.scheduled_service.delete_occurrence.assert_not_awaited()
    service.repository.save.assert_not_awaited()


async def test_confirm_overwrites_the_occurrence_when_consented(
    confirmation_service, receipt, user, confirm_payload
):
    service = confirmation_service
    confirm_payload.transaction_kind = "RECURRING"
    confirm_payload.frequency_unit = "MONTH"
    confirm_payload.frequency_interval = 1
    confirm_payload.overwrite = True
    previous = SimpleNamespace(
        id=uuid4(), settled_on=date(2025, 11, 13), value=Decimal("55.90")
    )
    service.scheduled_service.find_by.return_value = previous

    result = await service.confirm(receipt.id, user, confirm_payload)

    service.scheduled_service.delete_occurrence.assert_awaited_once_with(
        user=user, occurrence=previous
    )
    service.scheduled_service.add_owned.assert_awaited_once()
    assert result.occurrence is not None


async def test_confirm_propagates_failures_without_reporting_success(
    confirmation_service, receipt, user, confirm_payload
):
    service = confirmation_service
    service.payment_service.add_owned.side_effect = RuntimeError("database failure")

    with (
        patch("app.core.service.base.log_service_success") as success,
        pytest.raises(HTTPException) as caught,
    ):
        await service.confirm(receipt.id, user, confirm_payload)

    assert caught.value.status_code == 500
    service.repository.save.assert_not_awaited()
    assert receipt.status != ReceiptStatusEnum.PROCESSED
    assert all(
        entry.kwargs["operation"] != "confirm" for entry in success.call_args_list
    )


@pytest.mark.parametrize(
    "exception",
    [
        HTTPException(status_code=422, detail="Invalid receipt"),
        RuntimeError("upload failed"),
    ],
)
async def test_batch_continues_after_failed_upload_and_counts_statuses(
    user, service, receipt, exception
):
    files = [
        UploadFile(file=BytesIO(b"content"), filename=f"receipt-{index}.pdf")
        for index in range(2)
    ]
    uploaded = ReceiptUploadSchema(
        id=receipt.id,
        data=None,
        status=ReceiptStatusEnum.RECEIVED,
        errors=[],
        file_name=receipt.file_name,
        file_type=receipt.file_type,
        file_size=receipt.file_size,
    )
    service.upload = AsyncMock(side_effect=[exception, uploaded])

    result = await service.batch(files, user)

    assert result.total == 2
    assert result.failed == 1
    assert result.received == 1
    assert result.processed == result.processing == 0
    assert result.items[0].error_message == str(exception)
    assert result.items[0].file_name == files[0].filename
    assert result.items[1] is uploaded
    assert service.upload.await_count == 2


@pytest.fixture
def update_service(service, receipt):
    service.repository.find_by.return_value = receipt
    service.payment_service = AsyncMock()
    return service


async def test_update_receipt_persists_converted_data_and_returns_saved_entity(
    update_service, receipt, user, confirm_payload
):
    service = update_service
    original_id = receipt.id

    result = await service.update_receipt(receipt.id, user, confirm_payload)

    assert result is receipt
    assert receipt.id == original_id
    assert receipt.status == ReceiptStatusEnum.RECEIVED
    assert receipt.data["beneficiary"]["value"] == confirm_payload.beneficiary
    assert receipt.data["paid_amount"]["status"] == DataStatusEnum.FOUND
    assert (
        receipt.data["payment_date"]["value"]
        == confirm_payload.payment_date.isoformat()
    )
    service.payment_service.check_receipt.assert_awaited_once_with(receipt.id, user)
    service.repository.save.assert_awaited_once_with(entity=receipt, user_id=user.id)


async def test_update_receipt_marks_failed_when_required_field_is_missing(
    update_service, receipt, user, confirm_payload
):
    service = update_service
    confirm_payload.beneficiary = None

    result = await service.update_receipt(receipt.id, user, confirm_payload)

    assert result is receipt
    assert receipt.status == ReceiptStatusEnum.FAILED
    assert receipt.data["beneficiary"]["status"] == DataStatusEnum.NOT_FOUND
    service.repository.save.assert_awaited_once_with(entity=receipt, user_id=user.id)


async def test_update_receipt_does_not_touch_other_receipt_fields(
    update_service, receipt, user, confirm_payload
):
    service = update_service
    original = {
        "file_name": receipt.file_name,
        "file_type": receipt.file_type,
        "file_size": receipt.file_size,
        "file_hash": receipt.file_hash,
    }

    await service.update_receipt(receipt.id, user, confirm_payload)

    assert {name: getattr(receipt, name) for name in original} == original


async def test_update_receipt_returns_not_found_without_saving(
    update_service, user, confirm_payload
):
    service = update_service
    service.repository.find_by.return_value = None

    with pytest.raises(HTTPException) as caught:
        await service.update_receipt(uuid4(), user, confirm_payload)

    assert caught.value.status_code == 404
    service.repository.save.assert_not_awaited()
    service.payment_service.check_receipt.assert_not_awaited()


@pytest.mark.parametrize(
    "status", [ReceiptStatusEnum.PROCESSED, ReceiptStatusEnum.PROCESSING]
)
async def test_update_receipt_rejects_processed_or_processing_receipt(
    update_service, receipt, user, confirm_payload, status
):
    service = update_service
    receipt.status = status
    original_data = receipt.data

    with pytest.raises(HTTPException) as caught:
        await service.update_receipt(receipt.id, user, confirm_payload)

    assert caught.value.status_code == 409
    assert caught.value.detail == (
        "Receipt is processed or in processing and cannot be updated"
    )
    assert receipt.data == original_data
    assert receipt.status == status
    service.repository.save.assert_not_awaited()
    service.payment_service.check_receipt.assert_not_awaited()


@pytest.mark.parametrize(
    "status", [ReceiptStatusEnum.RECEIVED, ReceiptStatusEnum.FAILED]
)
async def test_update_receipt_allows_received_and_failed_receipts(
    update_service, receipt, user, confirm_payload, status
):
    service = update_service
    receipt.status = status

    result = await service.update_receipt(receipt.id, user, confirm_payload)

    assert result is receipt
    assert receipt.status == ReceiptStatusEnum.RECEIVED


async def test_update_receipt_rejects_receipt_that_already_has_a_payment(
    update_service, receipt, user, confirm_payload
):
    service = update_service
    service.payment_service.check_receipt.side_effect = HTTPException(
        409, "Receipt already has a payment"
    )

    with pytest.raises(HTTPException) as caught:
        await service.update_receipt(receipt.id, user, confirm_payload)

    assert caught.value.status_code == 409
    assert caught.value.detail == "Receipt already has a payment"
    service.repository.save.assert_not_awaited()


@pytest.mark.parametrize("operation", ["check_receipt", "save"])
async def test_update_receipt_propagates_failures_without_reporting_success(
    update_service, receipt, user, confirm_payload, operation
):
    service = update_service
    dependency = (
        service.payment_service.check_receipt
        if operation == "check_receipt"
        else service.repository.save
    )
    dependency.side_effect = RuntimeError("database failure")

    with (
        patch("app.core.service.base.log_service_success") as success,
        pytest.raises(HTTPException) as caught,
    ):
        await service.update_receipt(receipt.id, user, confirm_payload)

    assert caught.value.status_code == 500
    assert all(
        entry.kwargs["operation"] != "update_receipt"
        for entry in success.call_args_list
    )


async def test_update_receipt_commit_failure_never_reports_success(
    update_service, receipt, user, confirm_payload
):
    service = update_service

    @asynccontextmanager
    async def transaction():
        yield
        raise RuntimeError("commit failed")

    service.repository.transaction = transaction

    with (
        patch("app.core.service.base.log_service_success") as success,
        pytest.raises(HTTPException) as caught,
    ):
        await service.update_receipt(receipt.id, user, confirm_payload)

    assert caught.value.status_code == 500
    assert all(
        entry.kwargs["operation"] != "update_receipt"
        for entry in success.call_args_list
    )


async def test_update_receipt_preserves_category_sent_in_payload(
    update_service, receipt, user, confirm_payload
):
    service = update_service
    confirm_payload.category = "Utilities"

    await service.update_receipt(receipt.id, user, confirm_payload)

    assert receipt.data["category"] == {
        "value": "Utilities",
        "status": DataStatusEnum.FOUND.value,
    }


async def test_confirm_invalidates_entry_caches_only_after_commit(
    confirmation_service, receipt, user, confirm_payload
):
    service = confirmation_service
    events = []

    @asynccontextmanager
    async def transaction():
        yield
        events.append("commit")

    async def invalidate(_user, _entity, operation):
        events.append(f"invalidate:{operation}")

    service.repository.transaction = transaction
    service.transaction_service._invalidate_cache.side_effect = invalidate
    service.series_service._invalidate_cache.side_effect = invalidate
    service.scheduled_service._invalidate_cache.side_effect = invalidate

    await service.confirm(receipt.id, user, confirm_payload)

    assert events == ["commit", "invalidate:confirm"]


async def test_confirm_does_not_invalidate_caches_when_the_commit_fails(
    confirmation_service, receipt, user, confirm_payload
):
    service = confirmation_service

    @asynccontextmanager
    async def transaction():
        yield
        raise RuntimeError("commit failed")

    service.repository.transaction = transaction

    with pytest.raises(HTTPException):
        await service.confirm(receipt.id, user, confirm_payload)

    service.transaction_service._invalidate_cache.assert_not_awaited()
    service.series_service._invalidate_cache.assert_not_awaited()
    service.scheduled_service._invalidate_cache.assert_not_awaited()
