from pathlib import Path

from pydantic import TypeAdapter

from app.domain.credit_card.schema import CreditCardCreateSchema


def load_seeds_credit_cards() -> list[CreditCardCreateSchema]:
    catalog = Path(__file__).with_name("credit_cards.json")
    return TypeAdapter(list[CreditCardCreateSchema]).validate_json(
        catalog.read_text(encoding="utf-8")
    )
