from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.models import TransactionDirectionEnum, TransactionFrequencyUnitEnum


class TransactionSeedValueRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: Decimal = Field(gt=0, decimal_places=2)
    max: Decimal = Field(gt=0, decimal_places=2)

    @model_validator(mode="after")
    def validate_bounds(self) -> "TransactionSeedValueRange":
        if self.max < self.min:
            raise ValueError("Seed value range max must be at least min")
        return self


class SeedTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(min_length=1)
    weight: int = Field(gt=0)
    category_hint: str | None = Field(default=None, alias="categoryHint")


class TransactionSeedTemplate(SeedTemplate):
    direction: TransactionDirectionEnum
    value_range: TransactionSeedValueRange = Field(alias="valueRange")


class RecurrenceSeedTemplate(TransactionSeedTemplate):
    unit: TransactionFrequencyUnitEnum


class InstallmentsSeedRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: int = Field(ge=2, le=24, strict=True)
    max: int = Field(ge=2, le=24, strict=True)

    @model_validator(mode="after")
    def validate_bounds(self) -> "InstallmentsSeedRange":
        if self.max < self.min:
            raise ValueError("Seed installments range max must be at least min")
        return self


class InstallmentPlanSeedTemplate(SeedTemplate):
    total_range: TransactionSeedValueRange = Field(alias="totalRange")
    installments_range: InstallmentsSeedRange = Field(alias="installmentsRange")

    @model_validator(mode="after")
    def require_positive_installment_value(self) -> "InstallmentPlanSeedTemplate":
        if self.total_range.min * 100 < self.installments_range.max:
            raise ValueError("Seed total must allow at least one cent per installment")
        return self


def _load_catalog[TemplateT: SeedTemplate](
    filename: str, template_class: type[TemplateT]
) -> list[TemplateT]:
    catalog = Path(__file__).with_name(filename)
    templates = TypeAdapter(list[template_class]).validate_json(
        catalog.read_text(encoding="utf-8")
    )
    if not templates:
        raise ValueError(f"Seed catalog {filename} must not be empty")
    return templates


def load_seeds_transactions() -> list[TransactionSeedTemplate]:
    templates = _load_catalog("transactions.json", TransactionSeedTemplate)
    if {template.direction for template in templates} != set(TransactionDirectionEnum):
        raise ValueError("Transaction seed catalog must contain IN and OUT templates")
    return templates


def load_seeds_recurrences() -> list[RecurrenceSeedTemplate]:
    return _load_catalog("recurrences.json", RecurrenceSeedTemplate)


def load_seeds_installment_plans() -> list[InstallmentPlanSeedTemplate]:
    return _load_catalog("installment-plans.json", InstallmentPlanSeedTemplate)
