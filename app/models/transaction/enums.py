from enum import Enum

class TransactionStatusEnum(str, Enum):
    PENDING = "PENDING"
    SETTLED = "SETTLED"
    CANCELED = "CANCELED"

class TransactionDirectionEnum(str,  Enum):
    IN = "IN"
    OUT = "OUT"