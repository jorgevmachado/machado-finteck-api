from enum import StrEnum


class ProfileScope(StrEnum):
    SYSTEM = "system"
    PRIVATE = "private"


class ReceiptFieldName(StrEnum):
    FINE = "fine"
    PAYER = "payer"
    BARCODE = "barcode"
    DUE_DATE = "due_date"
    DISCOUNT = "discount"
    INTEREST = "interest"
    CATEGORY = "category"
    DESCRIPTION = "description"
    PAID_AMOUNT = "paid_amount"
    BENEFICIARY = "beneficiary"
    PAYMENT_DATE = "payment_date"
    TOTAL_CHARGES = "total_charges"
    AUTHENTICATION = "authentication"
    TRANSACTION_ID = "transaction_id"
    EFFECTIVE_PAYER = "effective_payer"
    DOCUMENT_AMOUNT = "document_amount"
    SOURCE_INSTITUTION = "source_institution"
    DESTINATION_INSTITUTION = "destination_institution"


class ReceiptParser(StrEnum):
    TEXT = "text"
    DECIMAL_BR = "decimal_br"
    DATE_NUMERIC_BR = "date_numeric_br"
    DATE_MONTH_NAME_PT_BR = "date_month_name_pt_br"


MONEY_FIELDS = frozenset(
    {
        ReceiptFieldName.FINE,
        ReceiptFieldName.DISCOUNT,
        ReceiptFieldName.INTEREST,
        ReceiptFieldName.PAID_AMOUNT,
        ReceiptFieldName.TOTAL_CHARGES,
        ReceiptFieldName.DOCUMENT_AMOUNT,
    }
)
DATE_FIELDS = frozenset({ReceiptFieldName.DUE_DATE, ReceiptFieldName.PAYMENT_DATE})
