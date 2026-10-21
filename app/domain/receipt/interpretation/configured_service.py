from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.receipt.interpretation.dynamic import interpret_isolated
from app.domain.receipt.interpretation.schema import InterpretationResult
from app.domain.receipt.receipt_interpretation_profile.repository import (
    ReceiptInterpretationProfileRepository,
)
from app.domain.receipt.receipt_interpretation_profile.schema import (
    ReceiptInterpretationProfileFilter,
    ReceiptInterpretationProfileSchema,
)


class ConfiguredInterpretationService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = ReceiptInterpretationProfileRepository(session)

    async def interpret(self, text: str, user_id: UUID) -> InterpretationResult:
        entities = await self.repository.list_all(
            ReceiptInterpretationProfileFilter(), user_id=user_id
        )
        profiles = [
            ReceiptInterpretationProfileSchema.model_validate(entity)
            for entity in entities
        ]
        if not any(
            profile.scope == "system" and profile.is_active for profile in profiles
        ):
            raise HTTPException(503, "Active General receipt profile is not configured")
        return await interpret_isolated(text, profiles)
