"""Pure semantic validation for LearningCorrection versioning from document 28.

A correction carries an immutable integer version and may reference the
previous correction it replaces. Self-supersession and non-positive or
non-integer versions are deny conditions. The check never mutates its input.
"""

from __future__ import annotations

from typing import Any

from .validator import ContractValidationError


def check_version(correction: dict[str, Any]) -> None:
    """Reject a correction with an invalid version or a self reference."""

    version = correction.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ContractValidationError("correction: version is invalid")
    supersedes = correction.get("supersedes")
    if supersedes is not None and supersedes == correction.get("correction_id"):
        raise ContractValidationError("correction: cannot supersede itself")
