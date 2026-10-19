from app.core.repository.base import BaseRepository
from app.models import Payer


class PayerRepository(BaseRepository[Payer]):
    model = Payer

    async def delete(self, entity: Payer) -> None:
        await self.session.delete(entity)
        await self.session.commit()
