from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models import Account
from app.temp import BaseRepository


class AccountRepository(BaseRepository[Account]):
    model = Account
    filter_fields = (
        "id",
        "name",
        "type",
        "is_active",
        "agency",
        "account_number",
        "financial_institution",
    )
    order_fields = ("id", "name", "created_at")
    default_order_by = "name"

    async def find_by_name(self, *, user_id: UUID, name: str) -> Account | None:
        # `name` não é único no banco; LIMIT 1 evita MultipleResultsFound
        # quando há duplicados por corrida — qualquer ocorrência já é duplicata.
        return await self.session.scalar(
            select(Account)
            .where(Account.user_id == user_id, Account.name == name)
            .limit(1)
        )
