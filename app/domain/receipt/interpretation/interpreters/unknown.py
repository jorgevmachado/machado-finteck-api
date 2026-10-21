from __future__ import annotations

from app.domain.receipt.data.schema import DataField
from app.domain.receipt.interpretation.interpreters.base import BaseInterpreter


class UnknownInterpreter(BaseInterpreter):
    @staticmethod
    def _extract_source_institution(text: str) -> DataField[str]:
        return UnknownInterpreter._extract_text("Unknown")
