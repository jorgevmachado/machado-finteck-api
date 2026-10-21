from __future__ import annotations

import asyncio
import multiprocessing
import re
import threading
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from multiprocessing.connection import Connection
from uuid import UUID

from app.domain.receipt.data.enums import DataStatusEnum
from app.domain.receipt.data.schema import DataField, ReceiptData
from app.domain.receipt.interpretation.schema import (
    InterpretationConfigurationSnapshot,
    InterpretationResult,
)
from app.domain.receipt.interpretation.validation import InterpretationValidator
from app.domain.receipt.receipt_interpretation_profile.enums import ReceiptParser
from app.domain.receipt.receipt_interpretation_profile.schema import (
    ReceiptConstantConfiguration,
    ReceiptFieldConfiguration,
    ReceiptFieldRuleSchema,
    ReceiptInterpretationProfileSchema,
    ReceiptNotFoundConfiguration,
)

MAX_TEXT_LENGTH = 1_000_000
MAX_PROFILES = 100
MAX_CONFIGURATION_BYTES = 4_000_000
EXECUTION_TIMEOUT_SECONDS = 5
_EXECUTION_SLOTS = threading.BoundedSemaphore(4)
MONTHS = {
    name: index
    for index, name in enumerate(
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


class ReceiptRuleExecutionError(RuntimeError):
    pass


def _not_found() -> DataField:
    return DataField(status=DataStatusEnum.NOT_FOUND)


def _parse(value: str, configuration: ReceiptFieldConfiguration) -> DataField:
    value = value.strip()
    if configuration.normalization == "remove_whitespace":
        value = re.sub(r"\s+", "", value)
    if not value:
        return DataField(status=DataStatusEnum.AMBIGUOUS)
    try:
        if configuration.parser == ReceiptParser.TEXT:
            parsed: str | Decimal | date = value
        elif configuration.parser == ReceiptParser.DECIMAL_BR:
            parsed = Decimal(value.replace(".", "").replace(",", "."))
            if not parsed.is_finite():
                raise ValueError("Non-finite amount")
        elif configuration.parser == ReceiptParser.DATE_NUMERIC_BR:
            parsed = datetime.strptime(value, "%d/%m/%Y").date()
        else:
            day, month, year = value.split()
            if configuration.normalization == "ocr_day":
                day = day.upper().translate(
                    str.maketrans({"N": "1", "I": "1", "L": "1"})
                )
            parsed = date(int(year), MONTHS[month.upper()], int(day))
    except (ValueError, InvalidOperation, KeyError, OverflowError):
        return DataField(status=DataStatusEnum.AMBIGUOUS)
    return DataField(value=parsed, status=DataStatusEnum.FOUND)


def _extract(text: str, rule: ReceiptFieldRuleSchema | None) -> DataField:
    if rule is None or isinstance(rule.configuration, ReceiptNotFoundConfiguration):
        return _not_found()
    configuration = rule.configuration
    if isinstance(configuration, ReceiptConstantConfiguration):
        return DataField(value=configuration.value, status=DataStatusEnum.FOUND)
    for pattern in configuration.patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group("value")
            if value is None:
                return DataField(status=DataStatusEnum.AMBIGUOUS)
            return _parse(value, configuration)
    return _not_found()


def interpret_profiles(
    text: str, profiles: list[ReceiptInterpretationProfileSchema]
) -> InterpretationResult:
    """Pure execution; production calls must use the isolated runner below."""
    active = [
        profile
        for profile in profiles
        if profile.is_active and profile.deleted_at is None
    ]
    generals = [profile for profile in active if profile.scope == "system"]
    if len(generals) != 1:
        raise ReceiptRuleExecutionError(
            "One active General receipt profile is required"
        )
    general = generals[0]
    scores: dict[UUID, int] = {}
    if text.strip():
        for profile in active:
            if profile.scope != "private":
                continue
            score = sum(
                rule.weight
                for rule in profile.identification_rules
                if rule.is_active
                and rule.deleted_at is None
                and re.search(rule.pattern, text, re.IGNORECASE)
            )
            if score:
                scores[profile.id] = score
    winners = [
        profile
        for profile in active
        if scores and scores.get(profile.id) == max(scores.values())
    ]
    selected = winners[0] if len(winners) == 1 else None
    rules: dict[str, ReceiptFieldRuleSchema] = {}
    for profile in (general, selected):
        if profile is not None:
            rules.update(
                (rule.field_name, rule)
                for rule in profile.field_rules
                if rule.is_active and rule.deleted_at is None
            )
    values = {
        name: _extract(text, rules.get(name)) if text.strip() else _not_found()
        for name in ReceiptData.model_fields
    }
    for name, rule in rules.items():
        configuration = rule.configuration
        if (
            isinstance(configuration, ReceiptFieldConfiguration)
            and configuration.fallback_field is not None
            and values[name].status != DataStatusEnum.FOUND
            and values[configuration.fallback_field].status == DataStatusEnum.FOUND
        ):
            values[name] = values[configuration.fallback_field].model_copy()
    result = InterpretationValidator.validate(ReceiptData.model_validate(values))
    result.configuration = InterpretationConfigurationSnapshot(
        selected_profile_id=selected.id if selected is not None else None,
        profiles=profiles,
    )
    return result


def _worker(connection: Connection, text: str, configuration: str) -> None:
    try:
        # A fresh Linux process bounds both catastrophic regex and memory growth.
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
        snapshot = InterpretationConfigurationSnapshot.model_validate_json(
            configuration
        )
        result = interpret_profiles(text, snapshot.profiles)
        connection.send(("ok", result.model_dump_json()))
    except Exception as exception:
        connection.send(("error", type(exception).__name__))
    finally:
        connection.close()


def _run_isolated(
    text: str, configuration: str, timeout: float = EXECUTION_TIMEOUT_SECONDS
) -> InterpretationResult:
    context = multiprocessing.get_context("spawn")
    if not _EXECUTION_SLOTS.acquire(timeout=timeout):
        raise ReceiptRuleExecutionError("Receipt rule execution capacity exhausted")
    reader, writer = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(writer, text, configuration))
    try:
        process.start()
        writer.close()
        if not reader.poll(timeout):
            raise ReceiptRuleExecutionError("Receipt rule execution timed out")
        try:
            status, payload = reader.recv()
        except EOFError as exception:
            raise ReceiptRuleExecutionError(
                "Receipt rule worker exited unexpectedly"
            ) from exception
        if status != "ok":
            raise ReceiptRuleExecutionError(f"Receipt rule worker failed: {payload}")
        return InterpretationResult.model_validate_json(payload)
    finally:
        reader.close()
        writer.close()
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join()
            process.close()
        _EXECUTION_SLOTS.release()


async def interpret_isolated(
    text: str, profiles: list[ReceiptInterpretationProfileSchema]
) -> InterpretationResult:
    if len(text) > MAX_TEXT_LENGTH:
        raise ReceiptRuleExecutionError(
            "Extracted receipt text exceeds execution limit"
        )
    if len(profiles) > MAX_PROFILES:
        raise ReceiptRuleExecutionError("Receipt profile count exceeds execution limit")
    configuration = InterpretationConfigurationSnapshot(
        selected_profile_id=None, profiles=profiles
    ).model_dump_json()
    if len(configuration.encode("utf-8")) > MAX_CONFIGURATION_BYTES:
        raise ReceiptRuleExecutionError(
            "Receipt rule configuration exceeds execution limit"
        )
    return await asyncio.to_thread(_run_isolated, text, configuration)
