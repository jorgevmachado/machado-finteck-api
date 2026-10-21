from app.domain.receipt.data.enums import DataStatusEnum
from app.domain.receipt.interpretation.interpreters.unknown import (
    UnknownInterpreter,
)

class TestUnknownInterpreter:
    def test_extract_source_institution_returns_unknown(self):
        result = UnknownInterpreter._extract_source_institution(
            "Documento de pagamento sem instituição identificada"
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "Unknown"

    def test_extract_source_institution_returns_unknown_for_empty_text(self):
        result = UnknownInterpreter._extract_source_institution("")

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "Unknown"
