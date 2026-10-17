from __future__ import annotations

from app.core.repository.base import BaseRepository
from app.models import Account


class AccountRepository(BaseRepository[Account]):
    model = Account

    async def delete(self, entity: Account) -> None:
        await self.session.delete(entity)
        await self.session.commit()
