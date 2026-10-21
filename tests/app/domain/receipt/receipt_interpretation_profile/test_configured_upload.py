from io import BytesIO
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from starlette.datastructures import Headers

from app.domain.receipt.interpretation.configured_service import (
    ConfiguredInterpretationService,
)
from app.domain.receipt.receipt_interpretation_profile.schema import (
    ReceiptInterpretationProfileUpdateSchema,
)
from app.domain.receipt.receipt_interpretation_profile.seed import seed_profiles
from app.domain.receipt.receipt_interpretation_profile.service import (
    ReceiptInterpretationProfileService,
)
from app.domain.receipt.repository import ReceiptRepository
from app.domain.receipt.service import ReceiptService
from app.models import Receipt, ReceiptStatusEnum
from tests.app.domain.receipt.receipt_interpretation_profile.conftest import create_user

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_configured_service_uses_only_current_owner_and_general(profile_sessions):
    async with profile_sessions() as session:
        owner = await create_user(session)
        other = await create_user(session)
        await seed_profiles(session, owner.id)
        service = ConfiguredInterpretationService(session)
        text = "NU PAGAMENTOS\nValor pago: R$ 10,00\nPara\nEmpresa\n05 FEV 2026"
        result = await service.interpret(text, owner.id)
        assert result.data.source_institution.value == "Nubank"
        assert len(result.configuration.profiles) == 4
        assert not result.errors
        # No private rules of the first owner may identify a bank for the second.
        other_result = await service.interpret(text, other.id)
        assert other_result.configuration.selected_profile_id is None
        assert other_result.data.source_institution.value is None
        nubank = next(
            p for p in result.configuration.profiles if p.institution_code == "NUBANK"
        )
        await ReceiptInterpretationProfileService.from_session(session).update(
            nubank.id,
            ReceiptInterpretationProfileUpdateSchema(is_active=False),
            owner,
        )
        updated = await service.interpret(text, owner.id)
        assert updated.configuration.selected_profile_id is None
        assert result.configuration.selected_profile_id == nubank.id


async def test_upload_uses_database_rules_persists_replay_snapshot_and_validates(
    profile_sessions,
):
    async with profile_sessions() as session:
        owner = await create_user(session)
        await seed_profiles(session, owner.id)
        service = ReceiptService(ReceiptRepository(session))
        service.extraction_service.extract = AsyncMock(
            return_value="ITAU UNIBANCO\nValor pago: R$ 50,00\n"
            "Nome do beneficiário: Empresa\nData do pagamento: 05/02/2026\n"
        )
        file = UploadFile(
            BytesIO(b"example upload content"),
            filename="receipt.pdf",
            headers=Headers({"content-type": "application/pdf"}),
        )
        uploaded = await service.upload(file, owner)
        assert uploaded.status == ReceiptStatusEnum.RECEIVED
        saved = await session.get(Receipt, uploaded.id)
        assert saved.data["source_institution"]["value"] == "Itaú"
        assert saved.data["_interpretation"]["version"] == 1
        assert len(saved.data["_interpretation"]["profiles"]) == 4
        assert saved.data["_interpretation"]["selected_profile_id"] is not None
        assert uploaded.data.payment_date.value.isoformat() == "2026-02-05"


async def test_missing_general_explicitly_blocks_upload_without_persisting(
    profile_sessions,
):
    async with profile_sessions() as session:
        owner = await create_user(session)
        service = ReceiptService(ReceiptRepository(session))
        service.extraction_service.extract = AsyncMock(return_value="text")
        file = UploadFile(
            BytesIO(b"upload"),
            filename="file.pdf",
            headers=Headers({"content-type": "application/pdf"}),
        )
        with pytest.raises(HTTPException) as caught:
            await service.upload(file, owner)
        assert caught.value.status_code == 503
        assert await session.scalar(select(func.count(Receipt.id))) == 0


async def test_dynamic_crud_rule_change_affects_next_receipt_without_cache(
    profile_sessions,
):
    async with profile_sessions() as session:
        owner = await create_user(session)
        await seed_profiles(session, owner.id)
        configured = ConfiguredInterpretationService(session)
        result = await configured.interpret("ITAU UNIBANCO", owner.id)
        itau = next(
            p for p in result.configuration.profiles if p.institution_code == "ITAU"
        )
        await ReceiptInterpretationProfileService.from_session(session).update(
            itau.id,
            ReceiptInterpretationProfileUpdateSchema(
                field_rules=[
                    {
                        "field_name": "source_institution",
                        "configuration": {"strategy": "constant", "value": "Meu Itau"},
                    }
                ]
            ),
            owner,
        )
        updated = await configured.interpret("ITAU UNIBANCO", owner.id)
        assert updated.data.source_institution.value == "Meu Itau"
        assert result.data.source_institution.value == "Itaú"
