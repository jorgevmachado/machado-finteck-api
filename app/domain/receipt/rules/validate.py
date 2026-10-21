import re

from app.shared.utils.string import text_strip


def normalize_name(value: str) -> str:
    value = text_strip(value)
    if not value:
        raise ValueError("Name cannot be empty")
    return value

def normalize_code(value: str) -> str:
    value = value.strip().upper()
    if re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,63}", value) is None:
        raise ValueError("Invalid institution code")
    return value

def validate_pattern(value: str) -> re.Pattern[str]:
    if not value.strip():
        raise ValueError("Pattern cannot be empty")
    try:
        return re.compile(value, re.IGNORECASE)
    except (re.error, RecursionError, OverflowError) as exception:
        raise ValueError("Invalid regular expression") from exception