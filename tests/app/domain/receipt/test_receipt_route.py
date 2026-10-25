from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import UploadFile

from app.domain.receipt.route import receipt_service, upload_receipt
from app.domain.receipt.service import ReceiptService


@pytest.mark.asyncio
async def test_receipt_service_dependency_binds_session_and_upload_delegates(user):
    session = MagicMock()
    service = receipt_service(session)
    assert isinstance(service, ReceiptService)
    assert service.repository is session
    assert service.rules_service.repository.session is session
    service.upload_receipt = AsyncMock()
    file = UploadFile(file=BytesIO(b"receipt"), filename="receipt.pdf")

    result = await upload_receipt(service=service, current_user=user, file=file)

    assert result is service.upload_receipt.return_value
    service.upload_receipt.assert_awaited_once_with(file=file, user=user)
