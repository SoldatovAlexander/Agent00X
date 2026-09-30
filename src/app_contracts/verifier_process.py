"""Bounded records for an experimental local verifier process handoff.

The records make the intended JSON boundary explicit. They do not provide
process isolation, verifier identity, or independent trust by themselves.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from .digests import sha256_bytes
from .executor import VerifierInput, VerifierResult


VERIFIER_PROCESS_SCHEMA_VERSION = 1

_REQUEST_FIELDS = frozenset({"schema_version", "verifier_input"})

_VERIFIER_INPUT_FIELDS = frozenset(
    {
        "process_id",
        "repository_id",
        "base_commit",
        "snapshot_tree_digest",
        "declared_change_paths",
        "verified_contents",
        "test_command",
        "test_timeout_seconds",
        "patch_digest",
        "evidence_digest",
        "verification_digest",
        "verified_contents_digest",
        "evidence_origin",
        "replay_result_digest",
    }
)

_STR_FIELDS = frozenset(
    {
        "process_id",
        "repository_id",
        "base_commit",
        "patch_digest",
        "evidence_digest",
        "verification_digest",
        "verified_contents_digest",
        "evidence_origin",
    }
)

_OPTIONAL_STR_FIELDS = frozenset({"snapshot_tree_digest", "replay_result_digest"})

_STR_LIST_FIELDS = frozenset({"declared_change_paths", "test_command"})


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


def parse_verifier_request(data: object) -> VerifierProcessRequest:
    """Parse canonical request bytes back into a bounded request record.

    Only the stated schema version and the exact verifier-input field set are
    accepted. Malformed encoding, JSON shape, duplicate keys and scalar types
    fail closed without echoing the payload or field values.
    """

    if type(data) is not bytes:
        raise VerifierProcessError("verifier process: request encoding is invalid")
    try:
        text = data.decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        raise VerifierProcessError("verifier process: request encoding is invalid") from None
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except Exception:
        raise VerifierProcessError("verifier process: request payload is invalid") from None
    if type(payload) is not dict:
        raise VerifierProcessError("verifier process: request payload is invalid")
    version = payload.get("schema_version")
    if type(version) is not int or version != VERIFIER_PROCESS_SCHEMA_VERSION:
        raise VerifierProcessError("verifier process: request version is invalid")
    if set(payload) != _REQUEST_FIELDS:
        raise VerifierProcessError("verifier process: request fields are invalid")
    raw_input = payload["verifier_input"]
    if type(raw_input) is not dict or set(raw_input) != _VERIFIER_INPUT_FIELDS:
        raise VerifierProcessError("verifier process: request fields are invalid")
    _validate_verifier_input_shape(raw_input)
    verifier_input = VerifierInput(
        process_id=raw_input["process_id"],
        repository_id=raw_input["repository_id"],
        base_commit=raw_input["base_commit"],
        snapshot_tree_digest=raw_input["snapshot_tree_digest"],
        declared_change_paths=tuple(raw_input["declared_change_paths"]),
        verified_contents=tuple(
            (entry[0], entry[1]) for entry in raw_input["verified_contents"]
        ),
        test_command=tuple(raw_input["test_command"]),
        test_timeout_seconds=raw_input["test_timeout_seconds"],
        patch_digest=raw_input["patch_digest"],
        evidence_digest=raw_input["evidence_digest"],
        verification_digest=raw_input["verification_digest"],
        verified_contents_digest=raw_input["verified_contents_digest"],
        evidence_origin=raw_input["evidence_origin"],
        replay_result_digest=raw_input["replay_result_digest"],
    )
    return VerifierProcessRequest(version, verifier_input)


def digest_verifier_request(value: object) -> str:
    """Return the canonical digest of one request's exact wire payload.

    The digest covers the same deterministic bytes the child would receive,
    so any field change between serialization and launch changes the digest.
    It is only a change-detection binding, not authentication of the child.
    """

    return sha256_bytes(serialize_verifier_request(value))


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError("non-standard JSON constant")


def _validate_verifier_input_shape(raw_input: dict[str, object]) -> None:
    for field in _STR_FIELDS:
        if type(raw_input[field]) is not str:
            raise VerifierProcessError("verifier process: request fields are invalid")
    for field in _OPTIONAL_STR_FIELDS:
        value = raw_input[field]
        if value is not None and type(value) is not str:
            raise VerifierProcessError("verifier process: request fields are invalid")
    if type(raw_input["test_timeout_seconds"]) is not int:
        raise VerifierProcessError("verifier process: request fields are invalid")
    for field in _STR_LIST_FIELDS:
        values = raw_input[field]
        if type(values) is not list or any(type(item) is not str for item in values):
            raise VerifierProcessError("verifier process: request fields are invalid")
    contents = raw_input["verified_contents"]
    if type(contents) is not list:
        raise VerifierProcessError("verifier process: request fields are invalid")
    for entry in contents:
        if (
            type(entry) is not list
            or len(entry) != 2
            or type(entry[0]) is not str
            or type(entry[1]) is not str
        ):
            raise VerifierProcessError("verifier process: request fields are invalid")
