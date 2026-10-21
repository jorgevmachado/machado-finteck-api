from app.domain.receipt.interpretation.institutions.rules.schema import (
    InstitutionRule,
)
from app.domain.receipt.interpretation.institutions.schema import (
    InstitutionEnum,
)


class CaixaRules:
    @staticmethod
    def rules() -> tuple[InstitutionRule, ...]:
        return (
            InstitutionRule(
                institution=InstitutionEnum.CAIXA,
                pattern=r"\bCAIXA\s+ECON[ÔO]MICA\s+FEDERAL\b",
                weight=100,
            ),
            InstitutionRule(
                institution=InstitutionEnum.CAIXA,
                pattern=r"\bVIA\s+INTERNET\s+BANKING\s+CAIXA\b",
                weight=90,
            ),
            InstitutionRule(
                institution=InstitutionEnum.CAIXA,
                pattern=r"\bAL[ÔO]\s+CAIXA\b",
                weight=100,
            ),
            InstitutionRule(
                institution=InstitutionEnum.CAIXA,
                pattern=r"\bSAC\s+CAIXA\b",
                weight=100,
            ),
        )
