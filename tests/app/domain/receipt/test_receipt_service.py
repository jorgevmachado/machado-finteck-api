from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from app.domain.receipt.data.enums import DataStatusEnum
from app.domain.receipt.data.schema import ReceiptData, ReceiptDataError
from app.domain.receipt.interpretation.schema import InterpretationResult
from app.domain.receipt.rules.schema import ReceiptRulesFilter, ReceiptRulesSchema
from app.domain.receipt.service import ReceiptService
from app.models import (
    ReceiptIdentificationRule,
    ReceiptInterpretationProfile,
)

MODULE = "app.domain.receipt.service"
pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("source", ["Nubank", None])
async def test_upload_interprets_extracted_text_with_active_user_rules(user, source):
    service = ReceiptService(MagicMock())
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
        result = await service.upload_receipt(file, user)

    service.rules_service.list_all.assert_awaited_once_with(
        ReceiptRulesFilter(is_active=True, limit=None), user
    )
    interpretation.assert_called_once_with(rules, "receipt text")
    assert rules[1].scope == "system"
    assert [rule.pattern for rule in rules[0].identification_rules] == ["bank"]
    interpretation.return_value.result.assert_called_once_with()
    assert result.data == expected.data
    assert result.errors == expected.errors
    assert result.filename == "receipt.pdf"
    assert result.user_id == user.id
    assert result.status == "processed"
    assert result.file_hash


async def test_upload_does_not_report_success_when_loading_rules_fails(user):
    service = ReceiptService(MagicMock())
    service.extraction_service = AsyncMock()
    service.extraction_service.extract.return_value = "receipt text"
    service.rules_service = AsyncMock()
    service.rules_service.list_all.side_effect = RuntimeError("database failure")
    with (
        patch(f"{MODULE}.validate_file", return_value=b"content"),
        patch(f"{MODULE}.log_service_success") as success,
        pytest.raises(HTTPException) as caught,
    ):
        await service.upload_receipt(
            UploadFile(file=BytesIO(b"content"), filename="receipt.pdf"), user
        )
    assert caught.value.status_code == 500
    success.assert_not_called()


async def test_find_by_uses_owner_context_for_operation_logging(user):
    service = ReceiptService(MagicMock())
    with patch(f"{MODULE}.log_service_success") as success:
        result = await service.find_by(user, "file-hash")
    assert result is None
    assert success.call_args.kwargs["user_request"] == user.username
    assert success.call_args.kwargs["operation"] == "find_by"
