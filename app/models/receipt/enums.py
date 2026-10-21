from enum import Enum


class ReceiptStatusEnum(str, Enum):
    FAILED = "FAILED"
    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    PROCESSING = "PROCESSING"
