from __future__ import annotations

import asyncio
import json
import re
import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.domain.receipt.rules.configuration.schema import (
    ReceiptConstantConfiguration,
    ReceiptFieldConfiguration,
    ReceiptNotFoundConfiguration,
)
from app.domain.receipt.rules.field.schema import ReceiptFieldRuleCreateSchema


class SourceExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str | None = None
    status: Literal["found", "not_found", "ambiguous"]


class SourceExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule: ReceiptFieldRuleCreateSchema
    text: str
    identified: bool


def extract_source_value(request: SourceExecutionRequest) -> SourceExtractionResult:
    rule = request.rule
    if rule.field_name != "source_institution":
        raise ValueError("Source engine only accepts source_institution")
    if not rule.is_active or isinstance(
        rule.configuration, ReceiptNotFoundConfiguration
    ):
        return SourceExtractionResult(status="not_found")
    configuration = rule.configuration
    if isinstance(configuration, ReceiptConstantConfiguration):
        return SourceExtractionResult(status="found", value=configuration.value)
    if isinstance(configuration, ReceiptFieldConfiguration):
        extraction = configuration
        mappings = []
    else:
        if request.identified:
            return SourceExtractionResult(
                status="found", value=configuration.identified_value
            )
        for match in configuration.matches:
            if match.contains.upper() in request.text.upper():
                return SourceExtractionResult(status="found", value=match.value)
        extraction = configuration.extraction
        mappings = configuration.mappings
    if extraction is not None:
        for pattern in extraction.patterns:
            match = re.search(pattern, request.text, re.IGNORECASE)
            if match is None:
                continue
            value = match.group("value")
            if value is None or not value.strip():
                return SourceExtractionResult(status="ambiguous")
            value = value.strip()
            for mapping in mappings:
                if mapping.contains.upper() in value.upper():
                    return SourceExtractionResult(status="found", value=mapping.value)
            return SourceExtractionResult(status="found", value=value)
    return SourceExtractionResult(status="not_found")


async def extract_source(
    rule: ReceiptFieldRuleCreateSchema, text: str, *, identified: bool
) -> SourceExtractionResult:
    if rule.field_name != "source_institution":
        raise ValueError("Source engine only accepts source_institution")
    if len(text) > 1_000_000:
        raise ValueError("Source text exceeds execution limit")
    request = SourceExecutionRequest(rule=rule, text=text, identified=identified)
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        __name__,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(request.model_dump_json().encode("utf-8")),
                timeout=3,
            )
        except TimeoutError as exception:
            raise RuntimeError("Source rule execution timed out") from exception
        if process.returncode != 0:
            raise RuntimeError("Source rule execution failed")
        return SourceExtractionResult.model_validate_json(stdout)
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()


def _main() -> None:
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    request = SourceExecutionRequest.model_validate(json.load(sys.stdin))
    sys.stdout.write(extract_source_value(request).model_dump_json())


if __name__ == "__main__":
    _main()
