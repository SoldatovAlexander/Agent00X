"""Small dependency-free validator for the JSON Schema subset used in M0.

The schemas remain Draft 2020-12 documents. This validator intentionally supports
only the keywords currently emitted by the project and fails on unknown schema
keywords, preventing accidental silent weakening when schemas evolve.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any


class ContractValidationError(ValueError):
    """Raised when a contract does not conform to its schema."""


_ANNOTATIONS = {"$schema", "$id", "title", "description"}
_SUPPORTED = _ANNOTATIONS | {
    "type", "additionalProperties", "required", "properties", "const", "enum",
    "pattern", "format", "minLength", "maxLength", "minimum", "minItems", "items",
}


def validate_schema(schema: Any, path: str = "$") -> None:
    """Fail closed on malformed schema declarations before any instance check.

    A malformed ``required``, ``properties`` or ``additionalProperties``
    declaration must never silently widen the accepted payload (for example a
    truthy ``additionalProperties`` string would disable unknown-field
    rejection), so structural violations raise RuntimeError deterministically.
    """

    if not isinstance(schema, dict):
        raise RuntimeError(f"invalid schema declaration at {path}: schema must be an object")
    unknown = set(schema) - _SUPPORTED
    if unknown:
        raise RuntimeError(f"unsupported schema keywords at {path}: {sorted(unknown)}")
    if "required" in schema:
        required = schema["required"]
        if not isinstance(required, list) or not all(isinstance(name, str) for name in required):
            raise RuntimeError(f"invalid schema declaration at {path}: required must be a list of strings")
    if "properties" in schema:
        properties = schema["properties"]
        if not isinstance(properties, dict) or not all(
            isinstance(name, str) and isinstance(subschema, dict) for name, subschema in properties.items()
        ):
            raise RuntimeError(f"invalid schema declaration at {path}: properties must map names to schemas")
        for name, subschema in properties.items():
            validate_schema(subschema, f"{path}.{name}")
    if "additionalProperties" in schema and not isinstance(schema["additionalProperties"], bool):
        raise RuntimeError(
            f"invalid schema declaration at {path}: additionalProperties must be a boolean"
        )
    if "items" in schema:
        validate_schema(schema["items"], f"{path}[]")


def validate(instance: Any, schema: dict[str, Any], path: str = "$") -> None:
    validate_schema(schema, path)
    _validate(instance, schema, path)


def _validate(instance: Any, schema: dict[str, Any], path: str = "$") -> None:
    unknown = set(schema) - _SUPPORTED
    if unknown:
        raise RuntimeError(f"unsupported schema keywords at {path}: {sorted(unknown)}")

    expected = schema.get("type")
    if expected is not None:
        matches = {
            "object": isinstance(instance, dict),
            "array": isinstance(instance, list),
            "string": isinstance(instance, str),
            "integer": isinstance(instance, int) and not isinstance(instance, bool),
            "boolean": isinstance(instance, bool),
        }.get(expected)
        if matches is None:
            raise RuntimeError(f"unsupported type {expected!r} at {path}")
        if not matches:
            raise ContractValidationError(f"{path}: expected {expected}")

    if "const" in schema and instance != schema["const"]:
        raise ContractValidationError(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        raise ContractValidationError(f"{path}: value is not in enum")

    if isinstance(instance, dict):
        required = schema.get("required", [])
        missing = [name for name in required if name not in instance]
        if missing:
            raise ContractValidationError(f"{path}: missing fields {missing}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(instance) - set(properties)
            if extra:
                raise ContractValidationError(f"{path}: unknown fields {sorted(extra)}")
        for name, value in instance.items():
            if name in properties:
                _validate(value, properties[name], f"{path}.{name}")

    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            raise ContractValidationError(f"{path}: too few items")
        if "items" in schema:
            for index, value in enumerate(instance):
                _validate(value, schema["items"], f"{path}[{index}]")

    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            raise ContractValidationError(f"{path}: string is too short")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            raise ContractValidationError(f"{path}: string is too long")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            raise ContractValidationError(f"{path}: pattern mismatch")
        if schema.get("format") == "date-time":
            try:
                datetime.fromisoformat(instance.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ContractValidationError(f"{path}: invalid date-time") from exc

    if "minimum" in schema:
        if isinstance(instance, bool):
            raise ContractValidationError(f"{path}: expected number")
        if isinstance(instance, int) and instance < schema["minimum"]:
            raise ContractValidationError(f"{path}: below minimum")
