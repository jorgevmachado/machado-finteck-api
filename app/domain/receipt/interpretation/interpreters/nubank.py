from __future__ import annotations

import re
from datetime import date

from app.domain.receipt.data.schema import DataField
from app.domain.receipt.interpretation.institutions.schema import (
    InstitutionEnum,
)
from app.domain.receipt.interpretation.interpreters.base import BaseInterpreter


class NubankInterpreter(BaseInterpreter):
    @staticmethod
    def _extract_due_date(text: str) -> DataField[date]:
        match = re.search(
            r"Vencimento\s+(\d{2})\s+([A-Z]{3})\s+(\d{4})",
            text,
            re.IGNORECASE,
        )

        if not match:
            return NubankInterpreter._not_found()
        day, month, year = match.groups()
        months = NubankInterpreter.MONTHS
        month_number = months.get(month.upper())
        if month_number is None:
            return NubankInterpreter._ambiguous()
        try:
            value = date(
                int(year),
                month_number,
                int(day),
            )
        except ValueError:
            return NubankInterpreter._ambiguous()
        return NubankInterpreter._parse_date(f"{value.day}/{value.month}/{value.year}")

    @staticmethod
    def _extract_payment_date(
        text: str,
    ) -> DataField[date]:
        match = re.search(
            r"([0-9NIL]{2})\s+([A-Z]{3})\s+(\d{4})(?:\s*-\s*\d{2}:\d{2}:\d{2})?",
            text,
            re.IGNORECASE,
        )

        if not match:
            return NubankInterpreter._not_found()

        day, month, year = match.groups()

        day = day.upper().translate(
            str.maketrans(
                {
                    "N": "1",
                    "I": "1",
                    "L": "1",
                }
            )
        )

        month_number = NubankInterpreter.MONTHS.get(month.upper())

        if month_number is None:
            return NubankInterpreter._ambiguous()

        try:
            value = date(
                int(year),
                month_number,
                int(day),
            )
        except ValueError:
            return NubankInterpreter._ambiguous()

        return NubankInterpreter._parse_date(f"{value.day}/{value.month}/{value.year}")

    @staticmethod
    def extract_source_institution(
        text: str, institution: InstitutionEnum = InstitutionEnum.UNKNOWN
    ) -> DataField[str]:
        if institution == InstitutionEnum.NUBANK:
            return NubankInterpreter._extract_text("Nubank")
        return NubankInterpreter._find_institution(
            text,
            "Nubank",
            (
                "NU PAGAMENTOS",
                "NUBANK.COM.BR",
            ),
        )
