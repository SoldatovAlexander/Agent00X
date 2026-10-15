#!/usr/bin/env python3
"""Render deterministic R5 source contexts without executing a Worker."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "fixtures/experiments/r5-fact-inventory.json"
_MAX_INVENTORY_BYTES = 65_536
_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_SOURCE_COMMIT = "2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e"
_CORRECTION = (
    "все database-bound numeric inputs валидируются строго как целые signed-64 "
    "значения до записи; некорректное или непредставимое значение даёт HTTP "
    "422 и ноль новых строк; корректный payload сохраняет прежнее поведение"
)
_SECURITY_LIMITS = [
    "Do not claim that the pinned source has verified signature or authorship.",
    "Only backend/routes.py may be changed in code-task scenarios.",
    "No credential, provider API, branch, pull request, push, or publication tool is available.",
    "Do not resolve conflicting acceptance and trusted-contract requirements; ask for clarification.",
]
_GROUPS = (
    ("endpoint-and-inputs", ("route.method-and-path", "route.telegram-default")),
    (
        "numeric-conversion",
        ("route.numeric-fields", "route.no-visible-numeric-validation"),
    ),
    ("persistence-and-response", ("route.database-write", "route.success-response")),
)
_EXPECTED_FACT_IDS = frozenset(fact_id for _, fact_ids in _GROUPS for fact_id in fact_ids)


class ContextRenderError(ValueError):
    """The pinned R5 inventory cannot be rendered under the fixed contract."""


def _load_inventory(path: str | Path = INVENTORY_PATH) -> dict[str, Any]:
    try:
        raw = Path(path).read_bytes()
        if not raw or len(raw) > _MAX_INVENTORY_BYTES:
            raise ValueError
        value = json.loads(raw)
        if type(value) is not dict or value.get("schema") != "agent00x-r5-fact-inventory/v1":
            raise ValueError
        source = value.get("source")
        if (
            type(source) is not dict
            or source.get("owner") != "SoldatovAlexander"
            or source.get("repository") != "brainbooster_full_v11"
            or source.get("commit") != _SOURCE_COMMIT
            or source.get("path") != "backend/routes.py"
            or source.get("retrieval") != "public-read-only"
            or source.get("signature_verified") is not False
        ):
            raise ValueError
        facts = value.get("facts")
        if type(facts) is not list or len(facts) != len(_EXPECTED_FACT_IDS):
            raise ValueError
        ids: list[str] = []
        for fact in facts:
            if type(fact) is not dict:
                raise ValueError
            fact_id = fact.get("id")
            if (
                type(fact_id) is not str
                or fact.get("kind") not in {"source-observation", "bounded-inference"}
                or type(fact.get("statement")) is not str
                or not fact["statement"]
                or len(fact["statement"]) > 1_000
                or type(fact.get("source_lines")) is not list
                or len(fact["source_lines"]) != 2
            ):
                raise ValueError
            first, last = fact["source_lines"]
            if (
                type(first) is not int
                or type(last) is not int
                or not 1 <= first <= last <= 24
            ):
                raise ValueError
            ids.append(fact_id)
        if len(ids) != len(set(ids)) or set(ids) != _EXPECTED_FACT_IDS:
            raise ValueError
        scope_note = value.get("scope_note")
        if type(scope_note) is not str or not scope_note or len(scope_note) > 1_000:
            raise ValueError
        return value
    except Exception:
        raise ContextRenderError("R5 context renderer: inventory rejected") from None


def render_context(
    *,
    layout: str,
    correction: bool,
    inventory_path: str | Path = INVENTORY_PATH,
) -> bytes:
    """Return canonical bytes for one structured/flat, correction/no-correction arm."""

    try:
        if layout not in {"structured", "flat"} or type(correction) is not bool:
            raise ValueError
        inventory = _load_inventory(inventory_path)
        facts = sorted(inventory["facts"], key=lambda fact: fact["id"])
        if layout == "structured":
            groups = [
                {
                    "id": group_id,
                    "facts": [
                        fact for fact in facts if fact["id"] in group_fact_ids
                    ],
                }
                for group_id, group_fact_ids in _GROUPS
            ]
            organization: dict[str, Any] = {"fact_groups": groups}
        else:
            organization = {"facts": facts}
        rendered: dict[str, Any] = {
            "schema": "agent00x-r5-rendered-context/v1",
            "layout": layout,
            "source": inventory["source"],
            "scope_note": inventory["scope_note"],
            "security_limits": list(_SECURITY_LIMITS),
            "tokenizer_status": "not_measured",
            **organization,
        }
        if correction:
            rendered["learning_correction"] = _CORRECTION
        return (
            json.dumps(
                rendered,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("ascii")
    except ContextRenderError:
        raise
    except Exception:
        raise ContextRenderError("R5 context renderer: request rejected") from None


def render_blinded_context(
    *,
    layout: str,
    correction: bool,
    inventory_path: str | Path = INVENTORY_PATH,
) -> bytes:
    """Render the pre-tokenization candidate without exposing its arm label."""

    try:
        if layout not in {"structured", "flat"} or type(correction) is not bool:
            raise ValueError
        inventory = _load_inventory(inventory_path)
        facts = sorted(inventory["facts"], key=lambda fact: fact["id"])
        category_labels = [group_id for group_id, _fact_ids in _GROUPS]
        fact_order = [fact["id"] for fact in facts]
        if layout == "structured":
            grouped_facts = [
                [fact for fact in facts if fact["id"] in fact_ids]
                for _group_id, fact_ids in _GROUPS
            ]
            rendered_facts: list[Any] = grouped_facts
        else:
            rendered_facts = facts
        rendered: dict[str, Any] = {
            "schema": "agent00x-r5-blinded-context/v1",
            "source": inventory["source"],
            "scope_note": inventory["scope_note"],
            "security_limits": list(_SECURITY_LIMITS),
            "tokenizer_status": "not_measured",
            "category_labels": category_labels,
            "fact_order": fact_order,
            "facts": rendered_facts,
        }
        if correction:
            rendered["learning_correction"] = _CORRECTION
        return (
            json.dumps(
                rendered,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("ascii")
    except ContextRenderError:
        raise
    except Exception:
        raise ContextRenderError("R5 blinded context renderer: request rejected") from None


def render_blinded_context_bundle(
    *, inventory_path: str | Path = INVENTORY_PATH
) -> dict[str, bytes]:
    """Return A/B/C/D only after their shared blinded-input contract is verified."""

    arms = (
        ("A", "structured", False),
        ("B", "flat", False),
        ("C", "structured", True),
        ("D", "flat", True),
    )
    try:
        inventory = _load_inventory(inventory_path)
        expected_facts = sorted(inventory["facts"], key=lambda fact: fact["id"])
        expected_ids = [fact["id"] for fact in expected_facts]
        expected_categories = [group_id for group_id, _fact_ids in _GROUPS]
        bundle: dict[str, bytes] = {}
        parsed: dict[str, dict[str, Any]] = {}
        for arm_id, layout, correction in arms:
            raw = render_blinded_context(
                layout=layout,
                correction=correction,
                inventory_path=inventory_path,
            )
            context = json.loads(raw)
            facts = context.get("facts")
            if layout == "structured":
                if type(facts) is not list or len(facts) != len(_GROUPS):
                    raise ValueError
                flattened = [fact for group in facts if type(group) is list for fact in group]
                expected_group_ids = [
                    sorted(group_fact_ids) for _group_id, group_fact_ids in _GROUPS
                ]
                if [[fact.get("id") for fact in group] for group in facts] != expected_group_ids:
                    raise ValueError
            else:
                if type(facts) is not list or any(type(fact) is not dict for fact in facts):
                    raise ValueError
                flattened = facts
            actual_ids = [fact.get("id") for fact in flattened if type(fact) is dict]
            if (
                len(flattened) != len(expected_facts)
                or len(actual_ids) != len(expected_ids)
                or len(set(actual_ids)) != len(expected_ids)
                or sorted(actual_ids) != expected_ids
                or sorted(flattened, key=lambda fact: fact["id"]) != expected_facts
                or context.get("schema") != "agent00x-r5-blinded-context/v1"
                or "layout" in context
                or "fact_groups" in context
                or context.get("category_labels") != expected_categories
                or context.get("fact_order") != expected_ids
                or context.get("source") != inventory["source"]
                or context.get("scope_note") != inventory["scope_note"]
                or context.get("security_limits") != _SECURITY_LIMITS
                or context.get("tokenizer_status") != "not_measured"
                or ("learning_correction" in context) is not correction
                or (correction and context.get("learning_correction") != _CORRECTION)
            ):
                raise ValueError
            bundle[arm_id] = raw
            parsed[arm_id] = context
        shared_keys = (
            "schema",
            "source",
            "scope_note",
            "security_limits",
            "tokenizer_status",
            "category_labels",
            "fact_order",
        )
        for key in shared_keys:
            if any(parsed[arm][key] != parsed["A"][key] for arm, _, _ in arms):
                raise ValueError
        for structured_arm, flat_arm in (("A", "B"), ("C", "D")):
            structured_facts = [
                fact for group in parsed[structured_arm]["facts"] for fact in group
            ]
            if sorted(structured_facts, key=lambda fact: fact["id"]) != parsed[flat_arm]["facts"]:
                raise ValueError
        return bundle
    except Exception:
        raise ContextRenderError("R5 blinded context bundle rejected") from None


def render_blinded_ordered_context_bundle(
    *, inventory_path: str | Path = INVENTORY_PATH
) -> dict[str, bytes]:
    """Render the v4 flat-array candidate with category-order boundaries."""

    try:
        source_bundle = render_blinded_context_bundle(inventory_path=inventory_path)
        source_structured = json.loads(source_bundle["A"])
        expected_facts = sorted(
            _load_inventory(inventory_path)["facts"], key=lambda fact: fact["id"]
        )
        source_facts = [
            fact
            for group in source_structured["facts"]
            for fact in group
        ]
        if (
            len(source_facts) != len(_EXPECTED_FACT_IDS)
            or sorted(source_facts, key=lambda fact: fact["id"]) != expected_facts
        ):
            raise ValueError

        structured_order: list[str] = []
        group_for_id: dict[str, str] = {}
        for group_id, group_fact_ids in _GROUPS:
            ordered_ids = sorted(group_fact_ids)
            structured_order.extend(ordered_ids)
            group_for_id.update({fact_id: group_id for fact_id in ordered_ids})
        by_id = {fact["id"]: fact for fact in source_facts}
        flat_order = sorted(by_id)
        if len(by_id) != len(_EXPECTED_FACT_IDS) or set(by_id) != _EXPECTED_FACT_IDS:
            raise ValueError

        bundle: dict[str, bytes] = {}
        parsed: dict[str, dict[str, Any]] = {}
        for arm_id in "ABCD":
            structured = arm_id in {"A", "C"}
            correction = arm_id in {"C", "D"}
            order = structured_order if structured else flat_order
            ordered_facts = [by_id[fact_id] for fact_id in order]
            context = json.loads(source_bundle[arm_id])
            context["schema"] = "agent00x-r5-blinded-context/v4"
            context.pop("layout", None)
            context["fact_order"] = order
            context["facts"] = ordered_facts
            if ("learning_correction" in context) is not correction:
                raise ValueError

            members: list[str] = []
            for key in sorted(context):
                if key == "facts":
                    separators = [
                        ",\n\n"
                        if structured and group_for_id[left] != group_for_id[right]
                        else ",\n"
                        for left, right in zip(order, order[1:])
                    ]
                    encoded_facts = [
                        json.dumps(
                            fact,
                            ensure_ascii=True,
                            allow_nan=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        for fact in ordered_facts
                    ]
                    value = "[" + "".join(
                        fact + (separators[index] if index < len(separators) else "")
                        for index, fact in enumerate(encoded_facts)
                    ) + "]"
                    if value.count("\n\n") != (2 if structured else 0):
                        raise ValueError
                else:
                    value = json.dumps(
                        context[key],
                        ensure_ascii=True,
                        allow_nan=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                members.append(json.dumps(key, ensure_ascii=True) + ":" + value)

            raw = ("{" + ",".join(members) + "}\n").encode("ascii")
            candidate = json.loads(raw)
            if (
                candidate.get("schema") != "agent00x-r5-blinded-context/v4"
                or candidate.get("fact_order") != order
                or [fact.get("id") for fact in candidate.get("facts", [])] != order
                or sorted(candidate.get("facts", []), key=lambda fact: fact["id"])
                != expected_facts
                or "layout" in candidate
                or "arm" in candidate
                or ("learning_correction" in candidate) is not correction
                or (
                    correction
                    and candidate.get("learning_correction") != _CORRECTION
                )
            ):
                raise ValueError
            bundle[arm_id] = raw
            parsed[arm_id] = candidate

        shared_keys = (
            "source",
            "scope_note",
            "security_limits",
            "tokenizer_status",
            "category_labels",
        )
        for key in shared_keys:
            if any(parsed[arm][key] != parsed["A"][key] for arm in "BCD"):
                raise ValueError
        for structured_arm, flat_arm in (("A", "B"), ("C", "D")):
            if sorted(
                parsed[structured_arm]["facts"], key=lambda fact: fact["id"]
            ) != parsed[flat_arm]["facts"]:
                raise ValueError
        return bundle
    except Exception:
        raise ContextRenderError(
            "R5 ordered blinded context bundle rejected"
        ) from None


def context_digest(context: bytes) -> str:
    if type(context) is not bytes or not context or len(context) > 131_072:
        raise ContextRenderError("R5 context renderer: context rejected")
    return "sha256:" + hashlib.sha256(context).hexdigest()
