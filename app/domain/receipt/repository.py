from app.core.repository import BaseRepository
from app.models import Receipt


class ReceiptRepository(BaseRepository[Receipt]):
    model = Receipt
    filter_fields = ("id", "file_hash", "status", "file_name", "file_type", "file_size")
    order_fields = (
        "id",
        "created_at",
        "received_at",
        "file_name",
        "file_size",
        "status",
    )
