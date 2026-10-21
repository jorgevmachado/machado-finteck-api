from pathlib import Path

from pydantic import TypeAdapter

from app.domain.receipt.rules.schema import ReceiptRulesSeedEntrySchema


def load_default_receipt_rules() -> list[ReceiptRulesSeedEntrySchema]:
    catalog = Path(__file__).with_name("default_receipt_rules.json")
    payloads = TypeAdapter(list[ReceiptRulesSeedEntrySchema]).validate_json(
        catalog.read_text(encoding="utf-8")
    )
    codes = [payload.institution_code for payload in payloads]
    if len(codes) != len(set(codes)):
        raise ValueError("Receipt seed catalog contains duplicate profile codes")
    return payloads
