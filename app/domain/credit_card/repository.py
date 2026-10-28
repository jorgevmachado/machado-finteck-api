from uuid import UUID

from sqlalchemy import select

from app.models import CreditCard
from app.temp import BaseRepository


class CreditCardRepository(BaseRepository[CreditCard]):
    model = CreditCard
    filter_fields = ("id", "name", "brand", "is_active")

    async def find_by_name(self, *, user_id: UUID, name: str) -> CreditCard | None:
        # `name` não é único no banco; LIMIT 1 evita MultipleResultsFound
        # quando há duplicados por corrida — qualquer ocorrência já é duplicata.
        return await self.session.scalar(
            select(CreditCard)
            .where(CreditCard.user_id == user_id, CreditCard.name == name)
            .limit(1)
        )
