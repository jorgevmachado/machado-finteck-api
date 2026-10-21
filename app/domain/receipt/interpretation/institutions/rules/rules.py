from app.domain.receipt.interpretation.institutions.rules.caixa import (
    CaixaRules,
)
from app.domain.receipt.interpretation.institutions.rules.itau import ItauRules
from app.domain.receipt.interpretation.institutions.rules.nubank import (
    NubankRules,
)

INSTITUTION_RULES = (
    *NubankRules.rules(),
    *ItauRules.rules(),
    *CaixaRules.rules(),
)
