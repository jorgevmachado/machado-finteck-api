from unittest.mock import MagicMock

from app.domain.receipt.data.enums import DataStatusEnum
from app.domain.receipt.data.schema import DataField
from app.domain.receipt.interpretation.institutions.schema import (
    InstitutionEnum,
)
from app.domain.receipt.interpretation.schema import (
    InterpretationResult,
)
from app.domain.receipt.interpretation.service import (
    InterpretationService,
)


class TestInterpretationServiceInterpret:
    def test_interpret_uses_itau_interpreter(self):
        service = InterpretationService()

        expected = MagicMock(spec=InterpretationResult)

        service.itau.interpret = MagicMock(return_value=MagicMock())
        service.unknown.interpret = MagicMock()

        from app.domain.receipt.interpretation.service import (
            InterpretationValidator,
        )

        original_validate = InterpretationValidator.validate

        try:
            InterpretationValidator.validate = MagicMock(
                return_value=expected,
            )

            result = service.interpret(text="ITAU UNIBANCO S.A.")

            assert result is expected
            service.itau.interpret.assert_called_once_with(
                text="ITAU UNIBANCO S.A.", institution=InstitutionEnum.ITAU
            )
            service.unknown.interpret.assert_not_called()
        finally:
            InterpretationValidator.validate = original_validate

    def test_interpret_uses_nubank_interpreter(self):
        service = InterpretationService()

        expected = MagicMock(spec=InterpretationResult)

        service.nubank.interpret = MagicMock(return_value=MagicMock())

        from app.domain.receipt.interpretation.service import (
            InterpretationValidator,
        )

        original_validate = InterpretationValidator.validate

        try:
            InterpretationValidator.validate = MagicMock(
                return_value=expected,
            )

            result = service.interpret("NU PAGAMENTOS S.A.")

            assert result is expected
            service.nubank.interpret.assert_called_once_with(
                text="NU PAGAMENTOS S.A.", institution=InstitutionEnum.NUBANK
            )
        finally:
            InterpretationValidator.validate = original_validate

    def test_interpret_uses_caixa_interpreter(self):
        service = InterpretationService()

        expected = MagicMock(spec=InterpretationResult)

        service.caixa.interpret = MagicMock(return_value=MagicMock())

        from app.domain.receipt.interpretation.service import (
            InterpretationValidator,
        )

        original_validate = InterpretationValidator.validate

        try:
            InterpretationValidator.validate = MagicMock(
                return_value=expected,
            )

            result = service.interpret("CAIXA ECONOMICA FEDERAL")

            assert result is expected
            service.caixa.interpret.assert_called_once_with(
                text="CAIXA ECONOMICA FEDERAL", institution=InstitutionEnum.CAIXA
            )
        finally:
            InterpretationValidator.validate = original_validate

    def test_interpret_uses_unknown_interpreter(self):
        service = InterpretationService()

        expected = MagicMock(spec=InterpretationResult)

        service.unknown.interpret = MagicMock(return_value=MagicMock())

        from app.domain.receipt.interpretation.service import (
            InterpretationValidator,
        )

        original_validate = InterpretationValidator.validate

        try:
            InterpretationValidator.validate = MagicMock(
                return_value=expected,
            )

            result = service.interpret("BANCO EXEMPLO S.A.")

            assert result is expected
            service.unknown.interpret.assert_called_once_with(
                text="BANCO EXEMPLO S.A.", institution=InstitutionEnum.UNKNOWN
            )
        finally:
            InterpretationValidator.validate = original_validate

    def test_interpret_uses_invalid_text_interpreter(self):
        service = InterpretationService()

        expected = MagicMock(spec=InterpretationResult)

        service.unknown.invalid_interpret = MagicMock(return_value=MagicMock())

        from app.domain.receipt.interpretation.service import (
            InterpretationValidator,
        )

        original_validate = InterpretationValidator.validate

        try:
            InterpretationValidator.validate = MagicMock(
                return_value=expected,
            )

            result = service.interpret("")

            assert result is expected
            service.unknown.invalid_interpret.assert_called_once()
        finally:
            InterpretationValidator.validate = original_validate


class TestInterpretationServiceConvertField:
    @staticmethod
    def test_convert_field_returns_found_when_value_exists():
        value = "Empresa Exemplo"

        result = InterpretationService._convert_field(value)

        assert isinstance(result, DataField)
        assert result.value == value
        assert result.status == DataStatusEnum.FOUND

    @staticmethod
    def test_convert_field_returns_not_found_when_value_is_none():
        result = InterpretationService._convert_field(None)

        assert isinstance(result, DataField)
        assert result.value is None
        assert result.status == DataStatusEnum.NOT_FOUND


class TestInterpretationServiceIdentifyInstitution:
    def test_identify_itau_by_unibanco_name(self):
        result = InterpretationService._identify_institution(
            "Instituição: ITAU UNIBANCO S.A."
        )

        assert result == InstitutionEnum.ITAU

    def test_identify_itau_by_accented_unibanco_name(self):
        result = InterpretationService._identify_institution(
            "Instituição: ITAÚ UNIBANCO S.A."
        )

        assert result == InstitutionEnum.ITAU

    def test_identify_itau_by_digital_authentication(self):
        result = InterpretationService._identify_institution(
            "AUTENTICAÇÃO DIGITAL ITAÚ: ABC123"
        )

        assert result == InstitutionEnum.ITAU

    def test_identify_nubank_by_nu_pagamentos(self):
        result = InterpretationService._identify_institution(
            "Favorecido: NU PAGAMENTOS SA"
        )

        assert result == InstitutionEnum.NUBANK

    def test_identify_nubank_by_nu_pagamentos_with_punctuation(self):
        result = InterpretationService._identify_institution(
            "Favorecido: NU PAGAMENTOS S.A."
        )

        assert result == InstitutionEnum.NUBANK

    def test_identify_nubank_by_domain(self):
        result = InterpretationService._identify_institution("Acesse NUBANK.COM.BR")

        assert result == InstitutionEnum.NUBANK

    def test_identify_caixa_by_economica_federal(self):
        result = InterpretationService._identify_institution(
            "Banco Recebedor: CAIXA ECONOMICA FEDERAL"
        )

        assert result == InstitutionEnum.CAIXA

    def test_identify_caixa_by_accented_economica_federal(self):
        result = InterpretationService._identify_institution(
            "Banco Recebedor: CAIXA ECONÔMICA FEDERAL"
        )

        assert result == InstitutionEnum.CAIXA

    def test_identify_caixa_by_internet_banking(self):
        result = InterpretationService._identify_institution(
            "Via Internet Banking CAIXA"
        )

        assert result == InstitutionEnum.CAIXA

    def test_identify_unknown_institution(self):
        result = InterpretationService._identify_institution("Banco Exemplo S.A.")

        assert result == InstitutionEnum.UNKNOWN

    def test_identify_nubank_origin_with_itau_destination(self):
        text = """
            Comprovante de pagamento
            Destino
            Nome NEOENERGIA BRASILIA
            Instituição ITAÚ UNIBANCO S.A.

            Origem
            Nome Jorge Luiz Vieira Machado da Silva
            Instituição NU PAGAMENTOS - IP
        """

        result = InterpretationService._identify_institution(text)

        assert result == InstitutionEnum.NUBANK

    def test_identify_nubank_origin_with_corrupted_ocr(self):
        text = """
            Comprovante de pagamento
            Destino
            Nome NEOENERGIA BRASILIA
            Instituição ITAÚ UNIBANCO S.A.

            Origem
            Nome Jorge Luiz Vieira Machado da Silva
            NU PAGAMENTOS |P
            CPF 123.456.789-00

            Nu Pagamentos S.A. - Instituição de Pagamento
            CNPJ 18.236.120/0001-58
        """

        result = InterpretationService._identify_institution(text)

        assert result == InstitutionEnum.NUBANK

    def test_identify_itau_origin_with_other_destination(self):
        text = """
            Comprovante de pagamento
            Destino
            Nome João da Silva
            Instituição NU PAGAMENTOS S.A.

            Origem
            Nome Maria da Silva
            Instituição ITAU UNIBANCO S.A.
        """

        result = InterpretationService._identify_institution(text)

        assert result == InstitutionEnum.ITAU

    def test_identify_caixa_origin(self):
        text = """
            Comprovante de pagamento
            Destino
            Nome João da Silva
            Instituição ITAU UNIBANCO S.A.

            Origem
            Nome Maria da Silva
            Banco CAIXA ECONOMICA FEDERAL
        """

        result = InterpretationService._identify_institution(text)

        assert result == InstitutionEnum.CAIXA

    def test_identify_unknown_when_origin_has_no_known_institution(self):
        text = """
            Comprovante de pagamento
            Destino
            Instituição ITAU UNIBANCO S.A.

            Origem
            Nome João da Silva
            Instituição BANCO EXEMPLO
        """

        result = InterpretationService._identify_institution(text)

        assert result == InstitutionEnum.UNKNOWN

    def test_identify_institution_returns_nubank_when_itau_is_processing_institution(
        self,
    ):
        text = """
        Comprovante de pagamento
        06 AGO 2026 - 16:13:05
        Valor R$ 164,38
        Manoel da Silva
        Pagador Pinto
        Documento
        Favorecido SEFAZ DISTRITO FEDER
        Código de barras
        856700000016643800091305826000048627281
        804612527
        NSU
        6362ebea-2e30-463e-a59a-58ebd89bbade
        Nu Pagamentos S.A.
        CNPJ 18.236.120/0001-58
        ID da transação: 6a74dcbf - ef54-474b-
        a4fa- Oba01edbcóba
        Recebido por correspondente bancário
        digital e processado por Itaú Unibanco S.A.
        Estamos aqui para ajudar se você tiver alguma
        dúvida.
        Me ajuda >
        Ouvidoria: 0800 887 0463 ou demais canais em
        nubank.com.br/contatostouvidoria
        """

        assert (
            InterpretationService._identify_institution(text) == InstitutionEnum.NUBANK
        )


class TestInterpretationServiceHasText:
    def test_has_text_returns_true_when_text_exists(self):
        assert InterpretationService._has_text("texto do comprovante") is True

    def test_has_text_returns_false_for_empty_text(self):
        assert InterpretationService._has_text("") is False

    def test_has_text_returns_false_for_whitespace(self):
        assert InterpretationService._has_text("   \n\t  ") is False
