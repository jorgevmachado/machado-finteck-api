from __future__ import annotations

from app.core.repository.base import BaseRepository
from app.models import CreditCard


class CreditCardRepository(BaseRepository[CreditCard]):
    model = CreditCard

    async def delete(self, entity: CreditCard) -> None:
        await self.session.delete(entity)
        await self.session.commit()
