from enum import Enum


class StatusEnum(str, Enum):
    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"
    INACTIVE = "INACTIVE"
