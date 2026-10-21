import re

from app.domain.receipt.interpretation.institutions.rules.rules import (
    INSTITUTION_RULES,
)
from app.domain.receipt.interpretation.institutions.schema import (
    InstitutionEnum,
    InstitutionRule,
)


class InstitutionsService:
    @staticmethod
    def identify(text: str) -> InstitutionEnum:
        normalized_text = text.upper()

        scores: dict[InstitutionEnum, int] = {}

        for rule in INSTITUTION_RULES:
            if InstitutionsService._matches(
                text=normalized_text,
                rule=rule,
            ):
                scores[rule.institution] = scores.get(rule.institution, 0) + rule.weight
        if not scores:
            return InstitutionEnum.UNKNOWN

        highest_score = max(scores.values())

        institutions = [
            institution
            for institution, score in scores.items()
            if score == highest_score
        ]

        if len(institutions) > 1:
            return InstitutionEnum.UNKNOWN

        return institutions[0]

    @staticmethod
    def _matches(text: str, rule: InstitutionRule) -> bool:
        return (
            re.search(
                rule.pattern,
                text,
            )
            is not None
        )
