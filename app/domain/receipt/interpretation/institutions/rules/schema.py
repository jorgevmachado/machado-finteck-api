from dataclasses import dataclass

from app.domain.receipt.interpretation.institutions.schema import (
    InstitutionEnum,
)


@dataclass(frozen=True)
class InstitutionRule:
    institution: InstitutionEnum
    pattern: str
    weight: int
