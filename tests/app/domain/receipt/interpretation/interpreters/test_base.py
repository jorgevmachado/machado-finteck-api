from datetime import date
from decimal import Decimal

from app.domain.receipt.data.enums import DataStatusEnum
from app.domain.receipt.interpretation.institutions.schema import (
    InstitutionEnum,
)
from app.domain.receipt.interpretation.interpreters.base import BaseInterpreter
 


class TestBaseInterpreter:
    def test_parse_date_returns_found(self):
        result = BaseInterpreter._parse_date("10/09/2026")

        assert result.status == DataStatusEnum.FOUND
        assert result.value == date(2026, 9, 10)

    def test_parse_date_returns_ambiguous_for_invalid_date(self):
        result = BaseInterpreter._parse_date("31/02/2026")

        assert result.status == DataStatusEnum.AMBIGUOUS
        assert result.value is None

    def test_parse_date_supports_custom_format(self):
        result = BaseInterpreter._parse_date(
            "2026-09-10",
            "%Y-%m-%d",
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == date(2026, 9, 10)

    def test_parse_decimal_returns_found(self):
        result = BaseInterpreter._parse_decimal("4.741,75")

        assert result.status == DataStatusEnum.FOUND
        assert result.value == Decimal("4741.75")

    def test_parse_decimal_returns_ambiguous_for_invalid_value(self):
        result = BaseInterpreter._parse_decimal("invalid")

        assert result.status == DataStatusEnum.AMBIGUOUS
        assert result.value is None

    def test_extract_money_field_accepts_single_pattern(self):
        result = BaseInterpreter._extract_money_field(
            "Valor: R$ 1.234,56",
            r"Valor:\s*R\$\s*([\d.]+,\d{2})",
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == Decimal("1234.56")

    def test_extract_money_field_accepts_multiple_patterns(self):
        result = BaseInterpreter._extract_money_field(
            "Valor pago: R$ 794,68",
            (
                r"Valor do documento:\s*R\$\s*([\d.]+,\d{2})",
                r"Valor pago:\s*R\$\s*([\d.]+,\d{2})",
            ),
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == Decimal("794.68")

    def test_extract_money_field_returns_not_found(self):
        result = BaseInterpreter._extract_money_field(
            "Documento sem valor",
            r"Valor:\s*R\$\s*([\d.]+,\d{2})",
        )

        assert result.status == DataStatusEnum.NOT_FOUND
        assert result.value is None

    def test_extract_date_field_accepts_single_pattern(self):
        result = BaseInterpreter._extract_date_field(
            "Vencimento 10/09/2026",
            r"Vencimento\s+(\d{2})/(\d{2})/(\d{4})",
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == date(2026, 9, 10)

    def test_extract_date_field_accepts_multiple_patterns(self):
        result = BaseInterpreter._extract_date_field(
            "Data do pagamento: 05/09/2026",
            (
                r"Data do documento:\s*(\d{2})/(\d{2})/(\d{4})",
                r"Data do pagamento:\s*(\d{2})/(\d{2})/(\d{4})",
            ),
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == date(2026, 9, 5)

    def test_extract_date_field_returns_not_found(self):
        result = BaseInterpreter._extract_date_field(
            "Sem data",
            r"Data:\s*(\d{2})/(\d{2})/(\d{4})",
        )

        assert result.status == DataStatusEnum.NOT_FOUND
        assert result.value is None

    def test_extract_text_returns_found(self):
        result = BaseInterpreter._extract_text("  JANNY DOE  ")

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "JANNY DOE"

    def test_extract_text_returns_ambiguous_for_empty_value(self):
        result = BaseInterpreter._extract_text("   ")

        assert result.status == DataStatusEnum.AMBIGUOUS
        assert result.value is None

    def test_extract_text_field_returns_found(self):
        result = BaseInterpreter._extract_text_field(
            "Nome: Jorge",
            r"Nome:\s*(.+)",
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "Jorge"

    def test_extract_text_field_accepts_multiple_patterns(self):
        result = BaseInterpreter._extract_text_field(
            "Favorecido Neoenergia",
            (
                r"Beneficiário:\s*(.+)",
                r"Favorecido\s+(.+)",
            ),
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "Neoenergia"

    def test_extract_text_field_returns_not_found(self):
        result = BaseInterpreter._extract_text_field(
            "Documento sem nome",
            r"Nome:\s*(.+)",
        )

        assert result.status == DataStatusEnum.NOT_FOUND
        assert result.value is None

    def test_not_found_returns_expected_field(self):
        result = BaseInterpreter._not_found()

        assert result.status == DataStatusEnum.NOT_FOUND
        assert result.value is None

    def test_ambiguous_returns_expected_field(self):
        result = BaseInterpreter._ambiguous()

        assert result.status == DataStatusEnum.AMBIGUOUS
        assert result.value is None

    def test_extract_fine(self):
        result = BaseInterpreter._extract_fine("Multa (R$): 20,00")

        assert result.status == DataStatusEnum.FOUND
        assert result.value == Decimal("20.00")

    def test_extract_fine_returns_not_found(self):
        result = BaseInterpreter._extract_fine("Multa não informada")

        assert result.status == DataStatusEnum.NOT_FOUND

    def test_interpret_uses_payer_as_effective_payer_and_document_amount_fallback(self):
        text = """Pagador
CPF: 999.999.999-99
Nome: JANNY DOE
Valor pago: R$ 120,00
"""

        result = BaseInterpreter().interpret(text, InstitutionEnum.UNKNOWN)

        assert result.payer.value == "JANNY DOE"
        assert result.effective_payer.value == "JANNY DOE"
        assert result.document_amount.value == Decimal("120.00")
        assert result.paid_amount.value == Decimal("120.00")

    def test_extract_payer_from_pagador_section(self):
        text = """\
Pagador
CPF: 999.999.999-99
Nome: JANNY DOE
"""

        result = BaseInterpreter._extract_payer(text)

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "JANNY DOE"

    def test_extract_payer_from_pagador_name(self):
        result = BaseInterpreter._extract_payer(
            "Nome do pagador: JORGE LUIZ VIEIRA DA SILVA FILHO"
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "JORGE LUIZ VIEIRA DA SILVA FILHO"

    def test_extract_payer_from_debited_account(self):
        text = """\
Dados da conta debitada
Nome JOHN DOE
Tipo de conta Conta corrente
"""

        result = BaseInterpreter._extract_payer(text)

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "JOHN DOE"

    def test_extract_payer_does_not_capture_pagador_final_efetivo(self):
        text = """\
 Pagador Final / Efetivo
 CPF: 999.999.999-99
 Nome: JANNY DOE
 """

        result = BaseInterpreter._extract_payer(text)

        assert result.status == DataStatusEnum.NOT_FOUND

    def test_extract_barcode_removes_spaces(self):
        text = "Código de barras: 4819000003 00431010578 61809280144 6"

        result = BaseInterpreter._extract_barcode(text)

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "481900000300431010578618092801446"

    def test_extract_barcode_supports_numeric_representation(self):
        text = (
            "Representação numérica do código de barras: "
            "00190000090360004100200002433175915650000474175"
        )

        result = BaseInterpreter._extract_barcode(text)

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "00190000090360004100200002433175915650000474175"

    def test_extract_barcode_returns_ambiguous_when_value_is_empty(self):
        result = BaseInterpreter._extract_barcode("Código de barras:   ")

        assert result.status == DataStatusEnum.AMBIGUOUS
        assert result.value is None

    def test_extract_due_date(self):
        result = BaseInterpreter._extract_due_date("Data do Vencimento: 10/09/2026")

        assert result.status == DataStatusEnum.FOUND
        assert result.value == date(2026, 9, 10)

    def test_extract_due_date_supports_vencimento_format(self):
        result = BaseInterpreter._extract_due_date("Vencimento 18/09/2026")

        assert result.status == DataStatusEnum.FOUND
        assert result.value == date(2026, 9, 18)

    def test_extract_discount(self):
        result = BaseInterpreter._extract_discount("Desconto (R$): 83,55")

        assert result.status == DataStatusEnum.FOUND
        assert result.value == Decimal("83.55")

    def test_extract_interest(self):
        result = BaseInterpreter._extract_interest("Juros (R$): 5,50")

        assert result.status == DataStatusEnum.FOUND
        assert result.value == Decimal("5.50")

    def test_extract_paid_amount(self):
        result = BaseInterpreter._extract_paid_amount("Valor pago: R$ 794,68")

        assert result.status == DataStatusEnum.FOUND
        assert result.value == Decimal("794.68")

    def test_extract_beneficiary(self):
        result = BaseInterpreter._extract_beneficiary(
            "Nome do beneficiário: CONDOMINIO EDIFICIO R M CARLO"
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "CONDOMINIO EDIFICIO R M CARLO"

    def test_extract_payment_date(self):
        result = BaseInterpreter._extract_payment_date("Data do pagamento: 05/09/2026")

        assert result.status == DataStatusEnum.FOUND
        assert result.value == date(2026, 9, 5)

    def test_extract_payment_date_supports_effective_date(self):
        result = BaseInterpreter._extract_payment_date(
            "Data de Efetivação / Agendamento: 03/09/2026"
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == date(2026, 9, 3)

    def test_extract_total_charges(self):
        result = BaseInterpreter._extract_total_charges("Total de encargos: R$ 10,00")

        assert result.status == DataStatusEnum.FOUND
        assert result.value == Decimal("10.00")

    def test_extract_transaction_id(self):
        result = BaseInterpreter._extract_transaction_id(
            "ID da transação: 6aa81d42-0310-4010-a9d4-546a86bff042"
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "6aa81d42-0310-4010-a9d4-546a86bff042"

    def test_extract_transaction_id_supports_operation_code(self):
        result = BaseInterpreter._extract_transaction_id(
            "Código da operação: 71207347056"
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "71207347056"

    def test_extract_effective_payer_from_itau_format(self):
        result = BaseInterpreter._extract_effective_payer(
            "Nome do pagador efetivo: JORGE LUIZ VIEIRA DA SILVA FILHO"
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "JORGE LUIZ VIEIRA DA SILVA FILHO"

    def test_extract_effective_payer_from_caixa_format(self):
        text = """\
 Pagador Final / Efetivo
 CPF: 999.999.999-99
 Nome: VERA LUCIA V MACHADO
 Representação numérica do código de barras:
 00190000090360004100
 """

        result = BaseInterpreter._extract_effective_payer(text)

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "VERA LUCIA V MACHADO"

    def test_extract_document_amount_from_itau_format(self):
        result = BaseInterpreter._extract_document_amount(
            "Valor do documento: R$ 878,23"
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == Decimal("878.23")

    def test_extract_document_amount_from_caixa_format(self):
        result = BaseInterpreter._extract_document_amount(
            "Valor Nominal do Boleto: 4.741,75"
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == Decimal("4741.75")

    def test_extract_destination_institution_from_itau_format(self):
        result = BaseInterpreter._extract_destination_institution(
            "Instituição Emissora: 481 - SUPERLÓGICA SCD S.A."
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "SUPERLÓGICA SCD S.A."

    def test_extract_destination_institution_from_caixa_format(self):
        text = """\
 Instituição Emissora - Nome do Banco: BANCO DO BRASIL S/A
 Código do Banco: 001
 """

        result = BaseInterpreter._extract_destination_institution(text)

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "BANCO DO BRASIL S/A"

    def test_extract_authentication_returns_not_found(self):
        result = BaseInterpreter._extract_authentication("Autenticação: ABC123")

        assert result.status == DataStatusEnum.NOT_FOUND
        assert result.value is None

    def test_extract_source_institution_returns_not_found(self):
        result = BaseInterpreter.extract_source_institution("CAIXA ECONOMICA FEDERAL")

        assert result.status == DataStatusEnum.NOT_FOUND
        assert result.value is None

    def test_find_institution_returns_found_value(self):
        result = BaseInterpreter._find_institution(
            "Banco do Brasil e Itaú",
            "Banco do Brasil",
            ("itaú", "banco do brasil"),
        )

        assert result.status == DataStatusEnum.FOUND
        assert result.value == "Banco do Brasil"

    def test_find_institution_returns_not_found_when_unknown(self):
        result = BaseInterpreter._find_institution(
            "Texto sem banco reconhecido",
            "Banco do Brasil",
            ("itaú", "nubank"),
        )

        assert result.status == DataStatusEnum.NOT_FOUND
        assert result.value is None

    def test_invalid_interpret_returns_not_found(self):
        constructor = BaseInterpreter()
        result = constructor.invalid_interpret()

        assert result.fine.status == DataStatusEnum.NOT_FOUND
        assert result.payer.status == DataStatusEnum.NOT_FOUND
        assert result.barcode.status == DataStatusEnum.NOT_FOUND
        assert result.due_date.status == DataStatusEnum.NOT_FOUND
        assert result.discount.status == DataStatusEnum.NOT_FOUND
        assert result.interest.status == DataStatusEnum.NOT_FOUND
        assert result.paid_amount.status == DataStatusEnum.NOT_FOUND
        assert result.beneficiary.status == DataStatusEnum.NOT_FOUND
        assert result.payment_date.status == DataStatusEnum.NOT_FOUND
        assert result.total_charges.status == DataStatusEnum.NOT_FOUND
        assert result.authentication.status == DataStatusEnum.NOT_FOUND
        assert result.transaction_id.status == DataStatusEnum.NOT_FOUND
        assert result.effective_payer.status == DataStatusEnum.NOT_FOUND
        assert result.document_amount.status == DataStatusEnum.NOT_FOUND
        assert result.source_institution.status == DataStatusEnum.NOT_FOUND
        assert result.destination_institution.status == DataStatusEnum.NOT_FOUND
