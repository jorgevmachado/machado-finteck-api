from app.models import Beneficiary
from app.temp import BaseRepository


class BeneficiaryRepository(BaseRepository[Beneficiary]):
    model = Beneficiary
    filter_fields = ("id", "name", "name_code")
