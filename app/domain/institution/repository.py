from app.core.repository.base import BaseRepository
from app.models import Institution


class InstitutionRepository(BaseRepository[Institution]):
    model = Institution

    async def delete(self, entity: Institution) -> None:
        await self.session.delete(entity)
        await self.session.commit()
