from app.domain.receipt.interpretation.institutions.rules.schema import (
    InstitutionRule,
)
from app.domain.receipt.interpretation.institutions.schema import (
    InstitutionEnum,
)


class NubankRules:
    @staticmethod
    def rules() -> tuple[InstitutionRule, ...]:
        return (
            InstitutionRule(
                institution=InstitutionEnum.NUBANK,
                pattern=r"\bNU\s+PAGAMENTOS(?:\s+S\.?A\.?)?\b",
                weight=100,
            ),
            InstitutionRule(
                institution=InstitutionEnum.NUBANK,
                pattern=r"\bNUBANK\.COM\.BR\b",
                weight=90,
            ),
            InstitutionRule(
                institution=InstitutionEnum.NUBANK,
                pattern=r"\bBANCO\s+NU\b",
                weight=80,
            ),
        )
