from __future__ import annotations

import re

from app.domain.receipt.data.schema import DataField
from app.domain.receipt.interpretation.institutions.schema import (
    InstitutionEnum,
)
from app.domain.receipt.interpretation.interpreters.base import BaseInterpreter

class CaixaInterpreter(BaseInterpreter):
    @staticmethod
    def extract_source_institution(
        text: str, institution: InstitutionEnum = InstitutionEnum.UNKNOWN
    ) -> DataField[str]:
        if institution == InstitutionEnum.CAIXA:
            return CaixaInterpreter._extract_text("Caixa")

        match = re.search(
            r"Banco Recebedor:\s*(.+?)(?=\n|Pagador Final)",
            text,
            re.IGNORECASE,
        )

        if not match:
            return CaixaInterpreter._not_found()

        value = match.group(1).strip()

        if "CAIXA ECONOMICA FEDERAL" in value.upper():
            return CaixaInterpreter._extract_text("Caixa")

        if "CAIXA ECONÔMICA FEDERAL" in value.upper():
            return CaixaInterpreter._extract_text("Caixa")

        return CaixaInterpreter._extract_text(value)
