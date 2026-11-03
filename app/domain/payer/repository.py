from app.models import Payer
from app.core.repository import BaseRepository


class PayerRepository(BaseRepository[Payer]):
    model = Payer
    filter_fields = ("id", "name", "name_code")
