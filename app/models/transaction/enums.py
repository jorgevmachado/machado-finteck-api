from enum import Enum

class TransactionStatusEnum(str, Enum):
    PENDING = "PENDING"
    SETTLED = "SETTLED"
    CANCELED = "CANCELED"

class TransactionDirectionEnum(str,  Enum):
    IN = "IN"
    OUT = "OUT"

class TransactionKindEnum(str,  Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"

class TransactionFrequencyUnitEnum(str, Enum):
    WEEK = "WEEK"
    MONTH = "MONTH"
    YEAR = "YEAR"