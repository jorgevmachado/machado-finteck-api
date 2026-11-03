from app.models import Beneficiary
from app.core.repository import BaseRepository


class BeneficiaryRepository(BaseRepository[Beneficiary]):
    model = Beneficiary
    filter_fields = ("id", "name", "name_code")
