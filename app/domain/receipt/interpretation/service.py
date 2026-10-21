from __future__ import annotations
import re

from app.domain.receipt.data.enums import DataStatusEnum
from app.domain.receipt.data.schema import ReceiptData, DataField
from app.domain.receipt.interpretation.institutions.schema import InstitutionEnum
from app.domain.receipt.interpretation.institutions.service import InstitutionsService
from app.domain.receipt.interpretation.interpreters.caixa import CaixaInterpreter
from app.domain.receipt.interpretation.interpreters.itau import ItauInterpreter
from app.domain.receipt.interpretation.interpreters.nubank import NubankInterpreter
from app.domain.receipt.interpretation.interpreters.unknown import UnknownInterpreter
from app.domain.receipt.interpretation.schema import InterpretationResult
from app.domain.receipt.interpretation.validation import InterpretationValidator


class InterpretationService:
    def __init__(self):
        self.itau = ItauInterpreter()
        self.nubank = NubankInterpreter()
        self.caixa = CaixaInterpreter()
        self.unknown = UnknownInterpreter()

    def interpret(self, text: str) -> InterpretationResult:
        if not self._has_text(text):
            data = self.unknown.invalid_interpret()
            return InterpretationValidator.validate(data)

        institution = InstitutionsService.identify(text)

        if institution == InstitutionEnum.UNKNOWN:
            institution = self._identify_institution(text)

        if institution == InstitutionEnum.ITAU:
            data = self.itau.interpret(text=text, institution=institution)
            return InterpretationValidator.validate(data)

        if institution == InstitutionEnum.NUBANK:
            data = self.nubank.interpret(text=text, institution=institution)
            return InterpretationValidator.validate(data)

        if institution == InstitutionEnum.CAIXA:
            data = self.caixa.interpret(text=text, institution=institution)
            return InterpretationValidator.validate(data)

        data = self.unknown.interpret(text=text, institution=InstitutionEnum.UNKNOWN)
        return InterpretationValidator.validate(data)

    def convert(self, data: dict[str, object]) -> ReceiptData:
        return ReceiptData(
            category=self._convert_field(data.get("category")),
            description=self._convert_field(data.get("description")),
            payment_date=self._convert_field(data.get("payment_date")),
            document_amount=self._convert_field(data.get("document_amount")),
            paid_amount=self._convert_field(data.get("paid_amount")),
            beneficiary=self._convert_field(data.get("beneficiary")),
            source_institution=self._convert_field(data.get("source_institution")),
            destination_institution=self._convert_field(
                data.get("destination_institution")
            ),
            due_date=self._convert_field(data.get("due_date")),
            discount=self._convert_field(data.get("discount")),
            interest=self._convert_field(data.get("interest")),
            fine=self._convert_field(data.get("fine")),
            total_charges=self._convert_field(data.get("total_charges")),
            payer=self._convert_field(data.get("payer")),
            effective_payer=self._convert_field(data.get("effective_payer")),
            barcode=self._convert_field(data.get("barcode")),
            authentication=self._convert_field(data.get("authentication")),
            transaction_id=self._convert_field(data.get("transaction_id")),
        )

    @staticmethod
    def _convert_field(value: object) -> DataField:
        return DataField(
            value=value,
            status=(
                DataStatusEnum.FOUND
                if value is not None
                else DataStatusEnum.NOT_FOUND
            ),
        )

    @staticmethod
    def _has_text(text: str) -> bool:
        return bool(text.strip())

    @staticmethod
    def _identify_institution(text: str) -> InstitutionEnum:
        normalized_text = text.upper()

        origin_match = re.search(
            r"\bORIGEM\b(.*?)(?=\bDESTINO\b|\Z)",
            normalized_text,
            re.DOTALL,
        )
        if origin_match:
            origin_text = origin_match.group(1)

            if re.search(r"NU\s+PAGAMENTOS", origin_text):
                return InstitutionEnum.NUBANK

            if re.search(r"ITA[ÚU]\s+UNIBANCO", origin_text):
                return InstitutionEnum.ITAU

            if re.search(
                    r"CAIXA\s+ECON[ÔO]MICA\s+FEDERAL",
                    origin_text,
            ):
                return InstitutionEnum.CAIXA

            return InstitutionEnum.UNKNOWN

        if re.search(r"NU\s+PAGAMENTOS\s+S\.?A", normalized_text):
            return InstitutionEnum.NUBANK

        if "NUBANK.COM.BR" in normalized_text:
            return InstitutionEnum.NUBANK

        if re.search(
                r"CAIXA\s+ECON[ÔO]MICA\s+FEDERAL",
                normalized_text,
        ):
            return InstitutionEnum.CAIXA

        if "VIA INTERNET BANKING CAIXA" in normalized_text:
            return InstitutionEnum.CAIXA

        if "AUTENTICAÇÃO DIGITAL ITAÚ" in normalized_text:
            return InstitutionEnum.ITAU

        if re.search(r"ITA[ÚU]\s+UNIBANCO", normalized_text):
            return InstitutionEnum.ITAU

        return InstitutionEnum.UNKNOWN
