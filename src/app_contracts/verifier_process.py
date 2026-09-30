"""Bounded records for an experimental local verifier process handoff.

The records make the intended JSON boundary explicit. They do not provide
process isolation, verifier identity, or independent trust by themselves.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from .executor import VerifierInput, VerifierResult


VERIFIER_PROCESS_SCHEMA_VERSION = 1


class VerifierProcessError(ValueError):
    """A verifier process record is malformed or unsupported."""


@dataclass(frozen=True)
class VerifierProcessRequest:
    """Versioned handoff containing only the existing bounded verifier input."""

    schema_version: int
    verifier_input: VerifierInput

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != VERIFIER_PROCESS_SCHEMA_VERSION:
            raise VerifierProcessError("verifier process: request version is invalid")
        if type(self.verifier_input) is not VerifierInput:
            raise VerifierProcessError("verifier process: request shape is invalid")

    @classmethod
    def from_verifier_input(cls, value: object) -> "VerifierProcessRequest":
        if type(value) is not VerifierInput:
            raise VerifierProcessError("verifier process: request shape is invalid")
        return cls(VERIFIER_PROCESS_SCHEMA_VERSION, value)


@dataclass(frozen=True)
class VerifierProcessResponse:
    """Versioned handoff containing one bounded typed verifier result."""

    schema_version: int
    verifier_result: VerifierResult

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != VERIFIER_PROCESS_SCHEMA_VERSION:
            raise VerifierProcessError("verifier process: response version is invalid")
        if type(self.verifier_result) is not VerifierResult:
            raise VerifierProcessError("verifier process: response shape is invalid")

    @classmethod
    def from_verifier_result(cls, value: object) -> "VerifierProcessResponse":
        if type(value) is not VerifierResult:
            raise VerifierProcessError("verifier process: response shape is invalid")
        return cls(VERIFIER_PROCESS_SCHEMA_VERSION, value)


def serialize_verifier_request(value: object) -> bytes:
    """Serialize one request to canonical UTF-8 JSON without mutating it."""

    if type(value) is not VerifierProcessRequest:
        raise VerifierProcessError("verifier process: request shape is invalid")
    try:
        encoded = json.dumps(
            asdict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except Exception:
        raise VerifierProcessError("verifier process: request serialization failed") from None
    return encoded
