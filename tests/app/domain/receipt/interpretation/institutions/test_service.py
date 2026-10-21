from app.domain.receipt.interpretation.institutions.schema import (
    InstitutionEnum,
    InstitutionRule,
)
from app.domain.receipt.interpretation.institutions.service import (
    InstitutionsService,
)


class TestInstitutionsServiceIdentifyNubank:
    @staticmethod
    def test_should_identify_nubank():
        text = """
        NU PAGAMENTOS S.A.
        NUBANK.COM.BR
        """

        assert InstitutionsService.identify(text) == InstitutionEnum.NUBANK


class TestInstitutionsServiceIdentifyUnknown:
    @staticmethod
    def test_should_return_unknown_when_there_is_no_evidence():
        text = """
        Comprovante de transferência
        """

        assert InstitutionsService.identify(text) == InstitutionEnum.UNKNOWN

    @staticmethod
    def test_should_return_unknown_when_institutions_have_same_score(monkeypatch):
        monkeypatch.setattr(
            "app.domain.receipt.interpretation.institutions.service.INSTITUTION_RULES",
            [
                InstitutionRule(
                    institution=InstitutionEnum.NUBANK,
                    pattern=r"NUBANK",
                    weight=10,
                ),
                InstitutionRule(
                    institution=InstitutionEnum.CAIXA,
                    pattern=r"CAIXA",
                    weight=10,
                ),
            ],
        )

        text = """
        NUBANK
        CAIXA
        """

        assert InstitutionsService.identify(text) == InstitutionEnum.UNKNOWN
