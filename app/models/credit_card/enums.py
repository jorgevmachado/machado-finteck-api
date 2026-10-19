from enum import Enum

class CreditCardBrandEnum(str, Enum):
    VISA = "VISA"
    MASTERCARD = "MASTERCARD"
    ELO = "ELO"
    AMEX = "AMEX"
    HIPERCARD = "HIPERCARD"
    DINERS = "DINERS"
    OTHER = "OTHER"