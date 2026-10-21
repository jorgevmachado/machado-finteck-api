from __future__ import annotations

import re

from app.domain.receipt.data.schema import DataField
from app.domain.receipt.interpretation.institutions.schema import (
    InstitutionEnum,
)
from app.domain.receipt.interpretation.interpreters.base import BaseInterpreter


class ItauInterpreter(BaseInterpreter):
    @staticmethod
    def _extract_authentication(
        text: str,
    ) -> DataField[str]:
        match = re.search(
            r"Autenticação(?: digital Itaú)?:\s*([A-Za-z0-9]+)", text, re.IGNORECASE
        )

        if not match:
            return ItauInterpreter._not_found()
        return ItauInterpreter._extract_text(match.group(1))

    @staticmethod
    def extract_source_institution(
        text: str, institution: InstitutionEnum = InstitutionEnum.UNKNOWN
    ) -> DataField[str]:
        if institution == InstitutionEnum.ITAU:
            return ItauInterpreter._extract_text("Itaú")
        return ItauInterpreter._find_institution(
            text,
            "Itaú",
            ("ITAU UNIBANCO", "ITAÚ UNIBANCO", "AUTENTICAÇÃO DIGITAL ITAÚ"),
        )
