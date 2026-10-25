from pydantic import BaseModel, ConfigDict

from app.domain.receipt.data.schema import ReceiptData, ReceiptDataError
from app.domain.receipt.rules.schema import ReceiptRulesSchema


class InstitutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution: str = "unknow"


class InterpretationResult(BaseModel):
    data: ReceiptData
    errors: list[ReceiptDataError]


class InterpretationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    rules: list[ReceiptRulesSchema]
