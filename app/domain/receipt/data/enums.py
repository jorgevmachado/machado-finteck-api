from enum import StrEnum


class DataStatusEnum(StrEnum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"