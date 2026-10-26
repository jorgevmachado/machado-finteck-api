from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict

from app.core.exceptions import handle_service_exception
from app.domain.receipt.data.enums import DataStatusEnum
from app.domain.receipt.data.schema import DataField, ReceiptData
from app.domain.receipt.interpretation.interpreter.rules.rules import merge_rules
from app.domain.receipt.rules.configuration.engine import (
    SourceExecutionRequest,
    extract_source_value,
)
from app.domain.receipt.rules.configuration.schema import ReceiptFieldConfiguration
from app.domain.receipt.rules.enums import ReceiptFieldName, ReceiptParser
from app.domain.receipt.rules.field.schema import ReceiptFieldRuleSchema
from app.domain.receipt.rules.schema import ReceiptRulesSchema

logger = logging.getLogger(__name__)
type FieldValue = str | date | Decimal


class InterpreterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    institution: str
    rules: list[ReceiptFieldRuleSchema]


class Interpreter:
    MONTHS = {
        month: number
        for number, month in enumerate(
            (
                "JAN",
                "FEV",
                "MAR",
                "ABR",
                "MAI",
                "JUN",
                "JUL",
                "AGO",
                "SET",
                "OUT",
                "NOV",
                "DEZ",
            ),
            start=1,
        )
    }

    def __init__(self, rules: list[ReceiptRulesSchema], institution: str):
        self.institution = institution
        self.rules = merge_rules(rules, institution)

    def interpret(self, text: str) -> ReceiptData:
        try:
            if len(text) > 1_000_000:
                raise ValueError("Receipt text exceeds execution limit")
            request = InterpreterRequest(
                text=text, institution=self.institution, rules=self.rules
            )
            process = subprocess.run(
                [sys.executable, "-m", __name__],
                input=request.model_dump_json().encode("utf-8"),
                capture_output=True,
                timeout=3,
                check=True,
            )
            return ReceiptData.model_validate_json(process.stdout)
        except (OSError, subprocess.SubprocessError, ValueError) as exception:
            handle_service_exception(
                exception,
                logger=logger,
                service="Interpreter",
                operation="interpret",
                raise_exception=False,
            )
            return ReceiptData.model_validate(
                {
                    field: DataField[FieldValue](status=DataStatusEnum.AMBIGUOUS)
                    for field in ReceiptFieldName
                }
            )

    @classmethod
    def _interpret(cls, request: InterpreterRequest) -> ReceiptData:
        rules = {
            rule.field_name: rule
            for rule in request.rules
            if rule.is_active and rule.deleted_at is None
        }
        fields = {
            name: cls._extract_field(rules.get(name), request.text, request.institution)
            for name in ReceiptFieldName
        }
        # Resolve fallbacks after all fields, regardless of the rule ordering.
        for name, rule in rules.items():
            configuration = rule.configuration
            if (
                isinstance(configuration, ReceiptFieldConfiguration)
                and configuration.fallback_field is not None
                and fields[name].status != DataStatusEnum.FOUND
            ):
                fallback = fields[ReceiptFieldName(configuration.fallback_field)]
                if fallback.status == DataStatusEnum.FOUND:
                    fields[name] = fallback.model_copy()
        return ReceiptData.model_validate(fields)

    @classmethod
    def _extract_field(
        cls, rule: ReceiptFieldRuleSchema | None, text: str, institution: str
    ) -> DataField[FieldValue]:
        if rule is None:
            return DataField(status=DataStatusEnum.NOT_FOUND)
        if rule.field_name == ReceiptFieldName.SOURCE_INSTITUTION:
            result = extract_source_value(
                SourceExecutionRequest(
                    rule=rule, text=text, identified=institution != "unknow"
                )
            )
            return DataField(
                value=result.value, status=DataStatusEnum(result.status.upper())
            )
        configuration = rule.configuration
        if not isinstance(configuration, ReceiptFieldConfiguration):
            return DataField(status=DataStatusEnum.NOT_FOUND)
        for pattern in configuration.patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match is None:
                continue
            value = match.group("value")
            if value is None:
                return DataField(status=DataStatusEnum.AMBIGUOUS)
            return cls._parse(value, configuration)
        return DataField(status=DataStatusEnum.NOT_FOUND)

    @classmethod
    def _parse(
        cls, value: str, configuration: ReceiptFieldConfiguration
    ) -> DataField[FieldValue]:
        value = value.strip()
        if configuration.normalization == "remove_whitespace":
            value = re.sub(r"\s+", "", value)
        if not value:
            return DataField(status=DataStatusEnum.AMBIGUOUS)
        try:
            parsed: FieldValue
            if configuration.parser == ReceiptParser.DECIMAL_BR:
                parsed = Decimal(value.replace(".", "").replace(",", "."))
                if not parsed.is_finite():
                    return DataField(status=DataStatusEnum.AMBIGUOUS)
            elif configuration.parser == ReceiptParser.DATE_NUMERIC_BR:
                parsed = datetime.strptime(value, "%d/%m/%Y").date()
            elif configuration.parser == ReceiptParser.DATE_MONTH_NAME_PT_BR:
                day, month, year = value.upper().split()
                if configuration.normalization == "ocr_day":
                    day = day.translate(str.maketrans({"N": "1", "I": "1", "L": "1"}))
                month_number = cls.MONTHS.get(month)
                if month_number is None:
                    return DataField(status=DataStatusEnum.AMBIGUOUS)
                parsed = date(int(year), month_number, int(day))
            else:
                parsed = value
        except (ValueError, InvalidOperation):
            return DataField(status=DataStatusEnum.AMBIGUOUS)
        return DataField(value=parsed, status=DataStatusEnum.FOUND)


def _main() -> None:
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    request = InterpreterRequest.model_validate(json.load(sys.stdin))
    sys.stdout.write(Interpreter._interpret(request).model_dump_json())


if __name__ == "__main__":
    _main()
