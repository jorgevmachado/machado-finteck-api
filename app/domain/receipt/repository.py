from app.core.repository.base import BaseRepository
from app.models import Receipt


class ReceiptRepository(BaseRepository[Receipt]):
    model = Receipt

    async def delete(self, entity: Receipt) -> None:
        await self.session.delete(entity)
        await self.session.commit()
