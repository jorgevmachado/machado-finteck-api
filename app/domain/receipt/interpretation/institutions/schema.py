from dataclasses import dataclass
from enum import StrEnum


class InstitutionEnum(StrEnum):
    ITAU = "itau"
    CAIXA = "caixa"
    NUBANK = "nubank"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class InstitutionRule:
    institution: InstitutionEnum
    pattern: str
    weight: int
