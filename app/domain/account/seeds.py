from pathlib import Path

from pydantic import TypeAdapter

from app.domain.account.schema import AccountCreateSchema


def load_seeds_accounts() -> list[AccountCreateSchema]:
    catalog = Path(__file__).with_name("accounts.json")
    return TypeAdapter(list[AccountCreateSchema]).validate_json(
        catalog.read_text(encoding="utf-8")
    )
