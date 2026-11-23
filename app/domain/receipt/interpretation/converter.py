from app.domain.receipt.interpretation.schema import InterpretationResult
from app.domain.receipt.interpretation.validation import InterpretationValidator
from app.domain.receipt.data.schema import DataField, ReceiptData
from app.domain.receipt.data.enums import DataStatusEnum


class Converter:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = self._convert_data(data)
        self.interpretation_validator = InterpretationValidator()

    def result(self) -> InterpretationResult:
        return self.interpretation_validator.validate(self.data)

    def _convert_data(self, data: dict[str, object]) -> ReceiptData:
        return ReceiptData(
            **{
                name: self._convert_field(data.get(name))
                for name in ReceiptData.model_fields
            }
        )

    @staticmethod
    def _convert_field(value: object) -> DataField:
        return DataField(
            value=value,
            status=DataStatusEnum.FOUND
            if value is not None
            else DataStatusEnum.NOT_FOUND,
        )
