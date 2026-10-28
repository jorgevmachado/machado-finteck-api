from app.models import Institution
from app.temp import BaseRepository


class InstitutionRepository(BaseRepository[Institution]):
    model = Institution
    filter_fields = ("id", "name", "name_code")
