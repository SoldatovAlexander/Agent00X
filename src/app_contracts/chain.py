"""Cross-contract invariants for the repository-change MVP chain."""

from __future__ import annotations

from typing import Any

from .digests import sha256_digest
from .validator import ContractValidationError


def validate_chain(chain: dict[str, dict[str, Any]]) -> None:
    names = (
        "process_contract", "identity", "capability_grant", "delegation_receipt",
        "trust_profile", "canonical_envelope", "task_contract",
        "evidence_bundle", "verification_report", "staged_change", "approval",
        "intent", "policy_decision", "actuator_request", "credential_use_grant",
        "action_receipt",
    )
    if not isinstance(chain, dict):
        raise ContractValidationError("chain: chain is malformed")
    missing = [name for name in names if name not in chain]
    if missing:
        raise ContractValidationError(f"chain: missing contracts {missing}")
    malformed = [name for name in names if not isinstance(chain[name], dict)]
    if malformed:
        raise ContractValidationError(f"chain: malformed contracts {malformed}")
    _require_members(chain)

    process_ids = {
        chain[name]["process_id"]
        for name in ("process_contract", "staged_change", "approval", "intent", "action_receipt")
    }
    _require_single("process_id", process_ids)

    if chain["identity"]["identity_id"] != chain["capability_grant"]["subject"]:
        raise ContractValidationError("chain: capability subject identity mismatch")
    if chain["identity"]["status"] != "active" or chain["capability_grant"]["status"] != "active":
        raise ContractValidationError("chain: inactive identity or capability grant")
    if chain["capability_grant"]["process_id"] != chain["process_contract"]["process_id"]:
        raise ContractValidationError("chain: capability process_id mismatch")
    if chain["delegation_receipt"]["parent_grant_id"] != chain["capability_grant"]["grant_id"]:
        raise ContractValidationError("chain: delegation parent grant mismatch")
    _validate_delegation(chain["capability_grant"], chain["delegation_receipt"])
    if chain["trust_profile"]["principal_id"] != chain["identity"]["identity_id"]:
        raise ContractValidationError("chain: trust profile principal mismatch")

    repositories = {
        chain[name]["repository_id"]
        for name in ("process_contract", "staged_change", "approval", "intent", "policy_decision", "action_receipt")
    }
    _require_single("repository_id", repositories)

    if chain["canonical_envelope"]["correlation_id"] != chain["process_contract"]["process_id"]:
        raise ContractValidationError("chain: envelope correlation_id mismatch")
    if chain["canonical_envelope"]["security"]["tainted"]:
        raise ContractValidationError("chain: tainted envelope cannot authorize publication")
    if chain["task_contract"]["process_id"] != chain["process_contract"]["process_id"]:
        raise ContractValidationError("chain: task process_id mismatch")
    if chain["evidence_bundle"]["task_id"] != chain["task_contract"]["task_id"]:
        raise ContractValidationError("chain: evidence task_id mismatch")
    if chain["evidence_bundle"]["patch_digest"] != chain["staged_change"]["patch_digest"]:
        raise ContractValidationError("chain: patch_digest mismatch")

    evidence_digest = sha256_digest(chain["evidence_bundle"])
    if chain["verification_report"]["evidence_digest"] != evidence_digest:
        raise ContractValidationError("chain: verification evidence digest mismatch")
    if chain["staged_change"]["evidence_digest"] != evidence_digest:
        raise ContractValidationError("chain: staged evidence digest mismatch")

    verification_digest = sha256_digest(chain["verification_report"])
    if chain["staged_change"]["verification_digest"] != verification_digest:
        raise ContractValidationError("chain: verification digest mismatch")
    if chain["verification_report"]["verdict"] != "pass":
        raise ContractValidationError("chain: only a passing verification can be staged")

    computed_staged_digest = sha256_digest(chain["staged_change"])
    referenced_staged_digests = {
        chain[name]["staged_change_digest"]
        for name in ("approval", "intent", "policy_decision", "action_receipt")
    }
    _require_single("staged_change_digest", referenced_staged_digests)
    if referenced_staged_digests != {computed_staged_digest}:
        raise ContractValidationError("chain: staged change digest does not match content")

    approval_id = chain["approval"]["approval_id"]
    if chain["intent"]["approval_id"] != approval_id or chain["action_receipt"]["approval_id"] != approval_id:
        raise ContractValidationError("chain: approval_id mismatch")

    decision_id = chain["policy_decision"]["decision_id"]
    if chain["action_receipt"]["policy_decision_id"] != decision_id:
        raise ContractValidationError("chain: policy_decision_id mismatch")
    if chain["policy_decision"]["effect"] != "allow":
        raise ContractValidationError("chain: receipt cannot reference a deny decision")

    intent = chain["intent"]
    request = chain["actuator_request"]
    for field in ("process_id", "repository_id", "base_commit", "staged_change_digest",
                  "approval_id", "branch_namespace", "title_artifact_ref",
                  "body_artifact_ref", "idempotency_key"):
        if request[field] != intent[field]:
            raise ContractValidationError(f"chain: actuator request {field} mismatch")
    if request["policy_decision_id"] != decision_id:
        raise ContractValidationError("chain: actuator request policy decision mismatch")
    if request["patch_artifact_ref"] != chain["staged_change"]["patch_artifact_ref"]:
        raise ContractValidationError("chain: actuator request patch mismatch")

    credential_grant = chain["credential_use_grant"]
    if credential_grant["actuator_id"] != request["actuator_id"]:
        raise ContractValidationError("chain: credential grant actuator mismatch")
    if credential_grant["repository_id"] != request["repository_id"]:
        raise ContractValidationError("chain: credential grant repository mismatch")
    if credential_grant["request_digest"] != sha256_digest(request):
        raise ContractValidationError("chain: credential grant request digest mismatch")

    expected_key = f"publish/{intent['process_id']}/{computed_staged_digest}"
    if intent["idempotency_key"] != expected_key:
        raise ContractValidationError("chain: intent idempotency key is not content-bound")
    if chain["action_receipt"]["idempotency_key"] != expected_key:
        raise ContractValidationError("chain: receipt idempotency key mismatch")


def _require_single(field: str, values: set[str]) -> None:
    if len(values) != 1:
        raise ContractValidationError(f"chain: {field} mismatch")


_REQUIRED_MEMBERS = {
    "process_contract": ("process_id", "repository_id"),
    "identity": ("identity_id", "status"),
    "capability_grant": (
        "subject", "status", "process_id", "grant_id",
        "delegable_actions", "resources", "max_delegation_depth",
    ),
    "delegation_receipt": (
        "parent_grant_id", "issuer", "process_id", "actions",
        "resources", "remaining_delegation_depth",
    ),
    "trust_profile": ("principal_id",),
    "canonical_envelope": ("correlation_id", "security"),
    "task_contract": ("process_id", "task_id"),
    "evidence_bundle": ("task_id", "patch_digest"),
    "verification_report": ("evidence_digest", "verdict"),
    "staged_change": (
        "process_id", "repository_id", "patch_digest", "evidence_digest",
        "verification_digest", "patch_artifact_ref",
    ),
    "approval": ("process_id", "repository_id", "staged_change_digest", "approval_id"),
    "intent": (
        "process_id", "repository_id", "staged_change_digest", "approval_id",
        "branch_namespace", "title_artifact_ref", "body_artifact_ref",
        "idempotency_key", "base_commit",
    ),
    "policy_decision": ("repository_id", "staged_change_digest", "decision_id", "effect"),
    "actuator_request": (
        "process_id", "repository_id", "base_commit", "staged_change_digest",
        "approval_id", "branch_namespace", "title_artifact_ref",
        "body_artifact_ref", "idempotency_key", "policy_decision_id",
        "patch_artifact_ref", "actuator_id",
    ),
    "credential_use_grant": ("actuator_id", "repository_id", "request_digest"),
    "action_receipt": (
        "process_id", "repository_id", "staged_change_digest", "approval_id",
        "policy_decision_id", "idempotency_key",
    ),
}


def _require_members(chain: dict[str, dict[str, Any]]) -> None:
    for name, fields in _REQUIRED_MEMBERS.items():
        member = chain[name]
        for field in fields:
            if field not in member:
                raise ContractValidationError(f"chain: {name} is missing {field}")
    security = chain["canonical_envelope"]["security"]
    if not isinstance(security, dict) or "tainted" not in security:
        raise ContractValidationError("chain: canonical_envelope is missing security.tainted")


def _validate_delegation(parent: dict[str, Any], child: dict[str, Any]) -> None:
    for holder, field in (
        (child, "actions"), (child, "resources"),
        (parent, "delegable_actions"), (parent, "resources"),
    ):
        if not isinstance(holder[field], (list, tuple)):
            raise ContractValidationError(f"chain: delegation {field} is malformed")
    for field in ("remaining_delegation_depth", "max_delegation_depth"):
        holder = child if field == "remaining_delegation_depth" else parent
        value = holder[field]
        if not isinstance(value, int) or isinstance(value, bool):
            raise ContractValidationError(f"chain: delegation {field} is malformed")
    if child["issuer"] != parent["subject"]:
        raise ContractValidationError("chain: delegation issuer mismatch")
    if child["process_id"] != parent["process_id"]:
        raise ContractValidationError("chain: delegation process mismatch")
    if not set(child["actions"]).issubset(parent["delegable_actions"]):
        raise ContractValidationError("chain: delegation expands actions")
    if not set(child["resources"]).issubset(parent["resources"]):
        raise ContractValidationError("chain: delegation expands resources")
    if child["remaining_delegation_depth"] >= parent["max_delegation_depth"]:
        raise ContractValidationError("chain: delegation depth is not reduced")
