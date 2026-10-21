from app.domain.receipt.interpretation.institutions.rules.schema import (
    InstitutionRule,
)
from app.domain.receipt.interpretation.institutions.schema import (
    InstitutionEnum,
)


class ItauRules:
    @staticmethod
    def rules() -> tuple[InstitutionRule, ...]:
        return (
            InstitutionRule(
                institution=InstitutionEnum.ITAU,
                pattern=r"\bITA[ÚU]\s+UNIBANCO\b",
                weight=100,
            ),
            InstitutionRule(
                institution=InstitutionEnum.ITAU,
                pattern=r"\bAUTENTICA[ÇC][ÃA]O\s+DIGITAL\s+ITA[ÚU]\b",
                weight=90,
            ),
            InstitutionRule(
                institution=InstitutionEnum.ITAU,
                pattern=r"\bITAU\.COM\.BR\b",
                weight=80,
            ),
        )
