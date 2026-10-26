from app.core.repository.base import BaseRepository
from app.models import Payment


class PaymentRepository(BaseRepository[Payment]):
    model = Payment

    async def delete(self, entity: Payment) -> None:
        await self.session.delete(entity)
        await self.session.commit()
