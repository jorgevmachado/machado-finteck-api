from datetime import date

from app.domain.receipt.data.enums import DataStatusEnum
from app.domain.receipt.interpretation.institutions.schema import (
    InstitutionEnum,
)
from app.domain.receipt.interpretation.interpreters.nubank import (
    NubankInterpreter,
)


class TestNubankInterpreter:
    def test_extract_due_date(self):
        result = NubankInterpreter._extract_due_date("Vencimento 18 SET 2026")

        assert result.status == DataStatusEnum.FOUND
        assert result.value == date(2026, 9, 18)

    def test_extract_due_date_supports_lowercase_month(self):
        result = NubankInterpreter._extract_due_date("Vencimento 18 set 2026")

        assert result.status == DataStatusEnum.FOUND
        assert result.value == date(2026, 9, 18)

    def test_extract_due_date_returns_not_found_without_due_date(self):
        result = NubankInterpreter._extract_due_date("Documento sem vencimento")

        assert result.status == DataStatusEnum.NOT_FOUND
        assert result.value is None

    def test_extract_due_date_returns_ambiguous_for_unknown_month(self):
        result = NubankInterpreter._extract_due_date("Vencimento 18 XYZ 2026")

        assert result.status == DataStatusEnum.AMBIGUOUS
        assert result.value is None

    def test_extract_due_date_returns_ambiguous_for_invalid_date(self):
        result = NubankInterpreter._extract_due_date("Vencimento 31 FEV 2026")

        assert result.status == DataStatusEnum.AMBIGUOUS
        assert result.value is None

    def test_extract_payment_date(self):
        result = NubankInterpreter._extract_payment_date("15 SET 2026 - 14:30:45")

        assert result.status == DataStatusEnum.FOUND
        assert result.value == date(2026, 9, 15)

    def test_extract_payment_date_supports_lowercase_month(self):
        result = NubankInterpreter._extract_payment_date("15 set 2026 - 14:30:45")

        assert result.status == DataStatusEnum.FOUND
        assert result.value == date(2026, 9, 15)

    def test_extract_payment_date_returns_not_found_without_timestamp(self):
        result = NubankInterpreter._extract_payment_date("Comprovante de pagamento")

        assert result.status == DataStatusEnum.NOT_FOUND
        assert result.value is None

    def test_extract_payment_date_returns_ambiguous_for_unknown_month(self):
        result = NubankInterpreter._extract_payment_date("15 XYZ 2026 - 14:30:45")

        assert result.status == DataStatusEnum.AMBIGUOUS
        assert result.value is None

    def test_extract_payment_date_returns_ambiguous_for_invalid_date(self):
        result = NubankInterpreter._extract_payment_date("31 FEV 2026 - 14:30:45")

        assert result.status == DataStatusEnum.AMBIGUOUS
        assert result.value is None

    def test_extract_source_institution_from_nu_pagamentos(self):
        result = NubankInterpreter.extract_source_institution(
            "Favorecido NU PAGAMENTOS SA"
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "Nubank"

    def test_extract_source_institution_from_nu_pagamentos_with_punctuation(
        self,
    ):
        result = NubankInterpreter.extract_source_institution(
            "Favorecido NU PAGAMENTOS S.A."
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "Nubank"

    def test_extract_source_institution_from_nubank_domain(self):
        result = NubankInterpreter.extract_source_institution(
            "Atendimento: NUBANK.COM.BR"
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "Nubank"

    def test_extract_source_institution_returns_not_found_when_nubank_is_absent(
        self,
    ):
        result = NubankInterpreter.extract_source_institution(
            "Favorecido BANCO EXEMPLO S.A."
        )

        assert result.status == DataStatusEnum.NOT_FOUND
        assert result.value is None

    def test_extract_source_institution_returns_from_institution_param(
        self,
    ):
        result = NubankInterpreter.extract_source_institution(
            text="Favorecido BANCO EXEMPLO S.A.", institution=InstitutionEnum.NUBANK
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "Nubank"
