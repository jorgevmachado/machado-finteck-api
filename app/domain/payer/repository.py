from app.models import Payer
from app.temp import BaseRepository


class PayerRepository(BaseRepository[Payer]):
    model = Payer
    filter_fields = ("id", "name", "name_code")
