from app.models import Institution
from app.core.repository import BaseRepository


class InstitutionRepository(BaseRepository[Institution]):
    model = Institution
    filter_fields = ("id", "name", "name_code")
