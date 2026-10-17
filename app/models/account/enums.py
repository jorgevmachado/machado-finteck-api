from enum import Enum

class AccountTypeEnum(str, Enum):
    CHECKING = "CHECKING"
    SAVINGS = "SAVINGS"
    CASH = "CASH"
    INVESTMENT = "INVESTMENT"
    OTHER = "OTHER"