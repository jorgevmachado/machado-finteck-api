from __future__ import annotations

import json
import logging
import re
import subprocess
import sys

from app.core.exceptions import handle_service_exception
from app.domain.receipt.interpretation.schema import (
    InstitutionResult,
    InterpretationRequest,
)
from app.domain.receipt.rules.schema import ReceiptRulesSchema

logger = logging.getLogger(__name__)


def _identify(text: str, rules: list[ReceiptRulesSchema]) -> str:
    scores: dict[str, int] = {}
    for profile in rules:
        if (
            not profile.is_active
            or profile.deleted_at is not None
            or profile.institution_code is None
        ):
            continue
        score = sum(
            rule.weight
            for rule in profile.identification_rules
            if rule.is_active
            and rule.deleted_at is None
            and re.search(rule.pattern, text, re.IGNORECASE) is not None
        )
        if score > 0:
            scores[profile.institution_code] = score
    if not scores:
        return "unknow"
    highest = max(scores.values())
    winners = [code for code, score in scores.items() if score == highest]
    return winners[0] if len(winners) == 1 else "unknow"


def find_institution(text: str, rules: list[ReceiptRulesSchema]) -> str:
    try:
        if len(text) > 1_000_000:
            raise ValueError("Receipt text exceeds execution limit")
        request = InterpretationRequest(text=text, rules=rules)
        process = subprocess.run(
            [sys.executable, "-m", __name__],
            input=request.model_dump_json().encode("utf-8"),
            capture_output=True,
            timeout=3,
            check=True,
        )
        return InstitutionResult.model_validate_json(process.stdout).institution
    except (OSError, subprocess.SubprocessError, ValueError) as exception:
        handle_service_exception(
            exception,
            logger=logger,
            service="Institution",
            operation="find_institution",
            raise_exception=False,
        )
        return "unknow"


def _main() -> None:
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    request = InterpretationRequest.model_validate(json.load(sys.stdin))
    result = InstitutionResult(institution=_identify(request.text, request.rules))
    sys.stdout.write(result.model_dump_json())


if __name__ == "__main__":
    _main()
