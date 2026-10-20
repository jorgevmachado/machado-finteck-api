from app.core.repository.base import BaseRepository
from app.models import Beneficiary


class BeneficiaryRepository(BaseRepository[Beneficiary]):
    model = Beneficiary

    async def delete(self, entity: Beneficiary) -> None:
        await self.session.delete(entity)
        await self.session.commit()
