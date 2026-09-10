"""Pure semantic validation for MemorySummary intervals from document 30.

Schema-valid date-time format alone cannot catch a reversed coverage period,
so this deterministic check rejects ``period_end`` before ``period_start``.
An equal instant is accepted as a zero-length summary; the function never
mutates its input and adds no sensitive fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .validator import ContractValidationError


def check_interval(summary: dict[str, Any]) -> None:
    """Reject a MemorySummary whose coverage interval runs backwards."""

    try:
        start = _parse_time(summary["period_start"])
        end = _parse_time(summary["period_end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractValidationError("summary: period boundary is invalid") from exc
    if end < start:
        raise ContractValidationError("summary: period_end is before period_start")


def _parse_time(value: str) -> datetime:
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("period boundary must be timezone-aware")
    return moment
