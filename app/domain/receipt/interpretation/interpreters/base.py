from __future__ import annotations

import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

from app.domain.receipt.data.enums import DataStatusEnum
from app.domain.receipt.data.schema import ReceiptData, DataField
from app.domain.receipt.interpretation.institutions.schema import InstitutionEnum


class BaseInterpreter:
    MONTHS = {
        "JAN": 1,
        "FEV": 2,
        "MAR": 3,
        "ABR": 4,
        "MAI": 5,
        "JUN": 6,
        "JUL": 7,
        "AGO": 8,
        "SET": 9,
        "OUT": 10,
        "NOV": 11,
        "DEZ": 12,
    }

    def interpret(
            self, text: str, institution: InstitutionEnum
    ) -> ReceiptData:
        payer = self._extract_payer(text)
        effective_payer = self._extract_effective_payer(text)
        if (
                effective_payer.status != DataStatusEnum.FOUND
                and payer.status == DataStatusEnum.FOUND
        ):
            effective_payer = payer

        document_amount = self._extract_document_amount(text)
        paid_amount = self._extract_paid_amount(text)
        if (
                document_amount.status != DataStatusEnum.FOUND
                and paid_amount.status == DataStatusEnum.FOUND
        ):
            document_amount = paid_amount
        return ReceiptData(
            fine=self._extract_fine(text),
            payer=payer,
            barcode=self._extract_barcode(text),
            category=self._extract_category(text),
            due_date=self._extract_due_date(text),
            discount=self._extract_discount(text),
            interest=self._extract_interest(text),
            description=self._extract_description(text),
            paid_amount=paid_amount,
            beneficiary=self._extract_beneficiary(text),
            payment_date=self._extract_payment_date(text),
            total_charges=self._extract_total_charges(text),
            authentication=self._extract_authentication(text),
            transaction_id=self._extract_transaction_id(text),
            effective_payer=effective_payer,
            document_amount=document_amount,
            source_institution=self.extract_source_institution(text, institution),
            destination_institution=self._extract_destination_institution(text),
        )

    def invalid_interpret(self) -> ReceiptData:
        return ReceiptData(
            fine=self._not_found(),
            payer=self._not_found(),
            barcode=self._not_found(),
            category=self._not_found(),
            due_date=self._not_found(),
            discount=self._not_found(),
            interest=self._not_found(),
            paid_amount=self._not_found(),
            beneficiary=self._not_found(),
            description=self._not_found(),
            payment_date=self._not_found(),
            total_charges=self._not_found(),
            authentication=self._not_found(),
            transaction_id=self._not_found(),
            effective_payer=self._not_found(),
            document_amount=self._not_found(),
            source_institution=self._not_found(),
            destination_institution=self._not_found(),
        )

    @staticmethod
    def _parse_date(value: str, format: str = "%d/%m/%Y") -> DataField[date]:
        try:
            parsed_date = datetime.strptime(value, format).date()
        except ValueError:
            return BaseInterpreter._ambiguous()

        return DataField(
            value=parsed_date,
            status=DataStatusEnum.FOUND,
        )

    @staticmethod
    def _parse_decimal(value: str) -> DataField[Decimal]:
        try:
            parsed_value = Decimal(value.replace(".", "").replace(",", "."))
        except InvalidOperation:
            return BaseInterpreter._ambiguous()

        return DataField(
            value=parsed_value,
            status=DataStatusEnum.FOUND,
        )

    @staticmethod
    def _extract_money_field(
            text: str, patterns: str | tuple[str, ...]
    ) -> DataField[Decimal]:
        if isinstance(patterns, str):
            patterns = (patterns,)

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)

            if match:
                return BaseInterpreter._parse_decimal(match.group(1))

        return BaseInterpreter._not_found()

    @staticmethod
    def _extract_date_field(
            text: str, patterns: str | tuple[str, ...]
    ) -> DataField[date]:
        if isinstance(patterns, str):
            patterns = (patterns,)

        for pattern in patterns:
            match = re.search(
                pattern,
                text,
                re.IGNORECASE,
            )

            if not match:
                continue

            day, month, year = match.groups()

            return BaseInterpreter._parse_date(f"{day}/{month}/{year}")
        return BaseInterpreter._not_found()

    @staticmethod
    def _extract_text_field(
            text: str, patterns: str | tuple[str, ...]
    ) -> DataField[str]:
        if isinstance(patterns, str):
            patterns = (patterns,)

        for pattern in patterns:
            match = re.search(
                pattern,
                text,
                re.IGNORECASE,
            )

            if not match:
                continue

            return BaseInterpreter._extract_text(match.group(1))

        return BaseInterpreter._not_found()

    @staticmethod
    def _extract_text(value: str) -> DataField[str]:
        value = value.strip()

        if not value:
            return BaseInterpreter._ambiguous()

        return DataField(
            value=value,
            status=DataStatusEnum.FOUND,
        )

    @staticmethod
    def _not_found() -> DataField:
        return DataField(value=None, status=DataStatusEnum.NOT_FOUND)

    @staticmethod
    def _ambiguous() -> DataField:
        return DataField(value=None, status=DataStatusEnum.AMBIGUOUS)

    @staticmethod
    def _find_institution(
            text: str, institution: str, patterns: tuple[str, ...]
    ) -> DataField[str]:
        normalized_text = text.upper()

        for pattern in patterns:
            if pattern.upper() in normalized_text:
                return DataField(
                    value=institution,
                    status=DataStatusEnum.FOUND,
                )

        return BaseInterpreter._not_found()

    # ---------------------------------------------------------#
    # Default implementations                                  #
    # ---------------------------------------------------------#

    @staticmethod
    def _extract_fine(text: str) -> DataField[Decimal]:
        return BaseInterpreter._extract_money_field(
            text,
            (
                r"Multa\s*\(R\$\):\s*([\d.]+,\d{2})",
                r"Multa:\s*R\$\s*([\d.]+,\d{2})",
            ),
        )

    @staticmethod
    def _extract_payer(text: str) -> DataField[str]:
        patterns = (
            r"Pagador\s*\n"
            r"CPF:\s*[^\n]+\n"
            r"Nome:\s*(.+?)(?=\n|$)",
            r"Nome do pagador:\s*(.+?)(?=\n|$)",
            r"Dados da conta debitada\s*\n"
            r"Nome\s+(.+?)(?=\n|$)",
        )
        for pattern in patterns:
            match = re.search(
                pattern,
                text,
                re.IGNORECASE,
            )
            if not match:
                continue

            value = match.group(1).strip()
            return BaseInterpreter._extract_text(value)

        return BaseInterpreter._not_found()

    @staticmethod
    def _extract_barcode(text: str) -> DataField[str]:
        patterns = (
            r"Código de barras\s*:?\s*([\d\s]+)",
            r"Representação numérica do código de barras:\s*([\d\s]+)",
        )
        for pattern in patterns:
            match = re.search(
                pattern,
                text,
                re.IGNORECASE | re.DOTALL,
            )

            if not match:
                continue

            value = re.sub(r"\s+", "", match.group(1))
            if not value:
                return BaseInterpreter._ambiguous()
            return BaseInterpreter._extract_text(value)
        return BaseInterpreter._not_found()

    @staticmethod
    def _extract_category(text: str) -> DataField[str]:
        return BaseInterpreter._not_found()

    @staticmethod
    def _extract_description(text: str) -> DataField[str]:
        return BaseInterpreter._not_found()

    @staticmethod
    def _extract_due_date(text: str) -> DataField[date]:
        return BaseInterpreter._extract_date_field(
            text,
            (
                r"Data\s+do\s+Vencimento:\s*(\d{2})/(\d{2})/(\d{4})",
                r"Data\s+de\s+vencimento:\s*(\d{2})/(\d{2})/(\d{4})",
                r"Vencimento\s+(\d{2})/(\d{2})/(\d{4})",
            ),
        )

    @staticmethod
    def _extract_discount(text: str) -> DataField[Decimal]:
        patterns = (
            r"Desconto:\s*R\$\s*([\d.]+,\d{2})",
            r"Desconto\s*\(R\$\):\s*([\d.]+,\d{2})",
        )
        return BaseInterpreter._extract_money_field(text, patterns)

    @staticmethod
    def _extract_interest(text: str) -> DataField[Decimal]:
        patterns = (
            r"Juros/Mora:\s*R\$\s*([\d.]+,\d{2})",
            r"Juros\s*\(R\$\):\s*([\d.]+,\d{2})",
        )
        return BaseInterpreter._extract_money_field(text, patterns)

    @staticmethod
    def _extract_paid_amount(text: str) -> DataField[Decimal]:
        return BaseInterpreter._extract_money_field(
            text,
            (
                r"Comprovante de Pix\s*\r?\n\s*R\$\s*([\d.]+,\d{2})",
                r"Valor pago:\s*R\$\s*([\d.]+,\d{2})",
                r"Valor Pago\s*\(R\$\):\s*([\d.]+,\d{2})",
                r"Valor\s+R\$\s*([\d.]+,\d{2})",
                r"Valor\s+Data\s*\r?\n\s*\d{2}/\d{2}/\d{2,4}\s*\r?\n\s*R\$\s*([\d.]+,\d{2})",
                r"Valor\s+Data\s*\r?\n\s*R\$\s*([\d.]+,\d{2})\s+\d{2}/\d{2}/\d{4}",
                r"R\$\s*([\d.]+,\d{2})",
            ),
        )

    @staticmethod
    def _extract_beneficiary(text: str) -> DataField[str]:
        return BaseInterpreter._extract_text_field(
            text,
            (
                r"Para\s*\r?\n\s*([^\r\n]+)",
                r"Destino\s*\r?\n\s*(?:Nome\s+)?([^\r\n]+)",
                r"Favorecido\s+(.+)",
                r"Favoreci\s+(.+)",
                r"Nome do beneficiário:\s*(.+?)(?=\n|$)",
                r"Beneficiário\s+(.+?)(?=\s+CNPJ\b)",
                r"Nome Fantasia:\s*(.+?)(?=\n|Razão Social:)",
                r"Razão Social:\s*(.+?)(?=\n|CNPJ:)",
                r"Nome da empresa\s*\r?\n\s*([^\r\n]+)",
                r"Beneficiário original\s*/\s*Cedente\s*\r?\n"
                r"Nome fantasia\s*\r?\n\s*[^\r\n]+\s*\r?\n"
                r"Nome\s*/\s*Razão social\s*\r?\n\s*([^\r\n]+)",
                r"Dados do recebedor\s*\r?\n\s*Nome\s*\r?\n\s*([^\r\n]+)",
                r"(Fatura do cartão Nubank)",
            ),
        )

    @staticmethod
    def _extract_payment_date(text: str) -> DataField[date]:
        return BaseInterpreter._extract_date_field(
            text,
            (
                r"Pagamento realizado em\s*:?\s*(\d{2})/(\d{2})/(\d{4})",
                r"Data do pagamento\s*:?\s*(\d{2})/(\d{2})/(\d{4})",
                r"Data\s+d[ae]\s+Efetivação\s*/\s*Agendamento\s*:?\s*"
                r"(\d{2})/(\d{2})/(\d{4})",
                r"Data\s+de\s+d[ée]bito\s*:?\s*(\d{2})/(\d{2})/(\d{4})",
                r"Data/\s*Hora\s*\r?\n\s*(\d{2})/(\d{2})/(\d{4})\s*-\s*\d{2}:\d{2}:\d{2}",
            ),
        )

    @staticmethod
    def _extract_total_charges(text: str) -> DataField[Decimal]:
        return BaseInterpreter._extract_money_field(
            text,
            r"Total de encargos:\s*R\$\s*([\d.]+,\d{2})",
        )

    @staticmethod
    def _extract_authentication(text: str) -> DataField[str]:
        return BaseInterpreter._not_found()

    @staticmethod
    def _extract_transaction_id(text: str) -> DataField[str]:
        patterns = (
            r"ID da transação:\s*([a-zA-Z0-9-]+)",
            r"Código da operação:\s*(\S+)",
        )
        return BaseInterpreter._extract_text_field(text, patterns)

    @staticmethod
    def _extract_effective_payer(text: str) -> DataField[str]:
        return BaseInterpreter._extract_text_field(
            text,
            (
                r"Nome do pagador efetivo:\s*(.+?)(?=\n|$)",
                r"Pagador Final\s*/\s*Efetivo"
                r"[\s\S]*?"
                r"Nome:\s*(.+?)(?=\n|Representação numérica)",
            ),
        )

    @staticmethod
    def _extract_document_amount(text: str) -> DataField[Decimal]:
        return BaseInterpreter._extract_money_field(
            text,
            (
                r"Valor do documento:\s*R\$\s*([\d.]+,\d{2})",
                r"Valor Nominal do Boleto:\s*([\d.]+,\d{2})",
            ),
        )

    @staticmethod
    def extract_source_institution(
            text: str, institution: InstitutionEnum = InstitutionEnum.UNKNOWN
    ) -> DataField[str]:
        return BaseInterpreter._not_found()

    @staticmethod
    def _extract_destination_institution(text: str) -> DataField[str]:
        return BaseInterpreter._extract_text_field(
            text,
            (
                r"Instituição Emissora:\s*\d+\s*-\s*(.+?)(?=\n|$)",
                r"Instituição Emissora\s*-\s*Nome do Banco:\s*"
                r"(.+?)(?=\n|Código do Banco:)",
            ),
        )
