from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
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
    repository.save.side_effect = lambda *, entity: entity
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
    service.rules_service.list_all.return_value = rules
    file = UploadFile(file=BytesIO(b"content"), filename="receipt.pdf")
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

    service.rules_service.list_all.assert_awaited_once_with(
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
    service.rules_service.list_all.side_effect = RuntimeError("database failure")
    with (
        patch(f"{MODULE}.validate_file", return_value=b"content"),
        patch.object(service, "find_by", return_value=None),
        patch(f"{MODULE}.log_service_success") as success,
        pytest.raises(HTTPException) as caught,
    ):
        await service.upload(
            UploadFile(file=BytesIO(b"content"), filename="receipt.pdf"), user
        )
    assert caught.value.status_code == 500
    success.assert_not_called()


async def test_find_by_uses_owner_context_for_operation_logging(user, service):
    with patch(f"{MODULE}.log_service_success") as success:
        result = await service.find_by(user, "file-hash")
    assert result is None
    assert success.call_args.kwargs["user_request"] == user.username
    assert success.call_args.kwargs["operation"] == "find_by"
    service.repository.find_by.assert_awaited_once_with(
        file_hash="file-hash", user_id=user.id
    )


@pytest.mark.parametrize("paginated", [True, False])
async def test_list_all_scopes_results_to_owner(user, service, receipt, paginated):
    page_filter = FilterPage.build(limit=2, offset=0, user_id=uuid4())
    expected = (
        CustomLimitOffsetPage.create(
            [receipt], total=1, params=LimitOffsetParams(limit=2, offset=0)
        )
        if paginated
        else [receipt]
    )
    service.repository.list_all.return_value = expected

    with patch(f"{MODULE}.log_service_success") as success:
        result = await service.list_all(page_filter, user)

    assert result is expected
    scoped_filter = service.repository.list_all.call_args.kwargs["page_filter"]
    assert scoped_filter.user_id == user.id
    assert scoped_filter.limit == 2
    assert scoped_filter.offset == 0
    assert page_filter.user_id != user.id
    assert success.call_args.kwargs["user_request"] == user.username


async def test_find_one_scopes_lookup_to_owner(user, service, receipt):
    service.repository.find_by.return_value = receipt

    assert await service.find_one(receipt.id, user) is receipt

    service.repository.find_by.assert_awaited_once_with(id=receipt.id, user_id=user.id)


async def test_find_one_not_found_returns_404(user, service):
    with pytest.raises(HTTPException) as caught:
        await service.find_one(uuid4(), user)

    assert caught.value.status_code == 404
    assert caught.value.detail == "Receipt not found"


@pytest.mark.parametrize("operation", ["list_all", "find_one"])
async def test_read_failure_is_logged_and_propagated(user, service, operation):
    repository_method = (
        service.repository.list_all
        if operation == "list_all"
        else service.repository.find_by
    )
    repository_method.side_effect = RuntimeError("database failure")
    with (
        patch(f"{MODULE}.log_service_success") as success,
        patch(
            f"{MODULE}.handle_service_exception", wraps=handle_service_exception
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

    service.repository.save.assert_awaited_once_with(entity=receipt)
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
