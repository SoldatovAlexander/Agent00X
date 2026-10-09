"""Read-only, digest-bound local preview for a persisted staged artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import unicodedata

from .durable_stage import (
    DurableStageStoreError,
    SQLiteStagedArtifactStore,
    StagedArtifact,
)
from .publication_seed import PublicationSeed, verifier_trust_intent_binding

_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_PREVIEW_BYTES = 2_500_000


class StagePreviewError(ValueError):
    """A requested local preview cannot be safely produced."""


def build_stage_preview(artifact: StagedArtifact) -> dict:
    """Return a detached review payload after revalidating the artifact."""
    if type(artifact) is not StagedArtifact:
        raise StagePreviewError("stage preview: artifact is invalid")
    try:
        validated = StagedArtifact(
            staged_change_digest=artifact.staged_change_digest,
            verified_contents_digest=artifact.verified_contents_digest,
            artifact_digest=artifact.artifact_digest,
            canonical_payload=artifact.canonical_payload,
        )
        payload = validated.payload_copy()
        seed = PublicationSeed(**payload["seed"])
        verifier = payload["verifier_result"]
        preview = {
            "schema": "stage-preview/v1",
            "stage": {
                "staged_change_digest": validated.staged_change_digest,
                "artifact_digest": validated.artifact_digest,
                "verified_contents_digest": validated.verified_contents_digest,
            },
            "change": {
                "process_id": seed.process_id,
                "repository_id": seed.repository_id,
                "base_commit": seed.base_commit,
                "declared_change_paths": payload["declared_change_paths"],
                "patch": payload["patch"],
            },
            "verification": {
                "verifier_id": verifier["verifier_id"],
                "verdict": verifier["verdict"],
                "verification_digest": verifier["verification_digest"],
            },
            "verifier_trust": verifier_trust_intent_binding(
                seed,
                signed_evidence_available=(
                    type(payload.get("verifier_trust_evidence")) is dict
                ),
            ),
            "approval": "not_created",
            "publication": "not_attempted",
        }
        encoded = json.dumps(
            preview, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2
        ).encode("utf-8")
        if len(encoded) > MAX_PREVIEW_BYTES:
            raise StagePreviewError("stage preview: output exceeds size limit")
        return preview
    except StagePreviewError:
        raise
    except Exception:
        raise StagePreviewError("stage preview: artifact is invalid") from None


def render_stage_preview(artifact: StagedArtifact) -> str:
    """Render a deterministic bounded JSON review record."""
    preview = build_stage_preview(artifact)
    return json.dumps(preview, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)


def _terminal_safe_text(value: str) -> str:
    """Escape terminal controls and directional formatting in reviewed text."""
    if type(value) is not str:
        raise StagePreviewError("stage preview: artifact is invalid")
    rendered = []
    for character in value:
        category = unicodedata.category(character)
        if character == "\n":
            rendered.append(character)
        elif category.startswith("C") or category in {"Zl", "Zp"}:
            codepoint = ord(character)
            rendered.append(
                f"\\u{codepoint:04x}" if codepoint <= 0xFFFF else f"\\U{codepoint:08x}"
            )
        else:
            rendered.append(character)
    return "".join(rendered)


def render_stage_preview_text(artifact: StagedArtifact) -> str:
    """Render a bounded, colorless terminal review without approval effects."""
    preview = build_stage_preview(artifact)
    stage = preview["stage"]
    change = preview["change"]
    verification = preview["verification"]
    paths = change["declared_change_paths"]
    if type(paths) is not list or not paths or any(type(path) is not str for path in paths):
        raise StagePreviewError("stage preview: artifact is invalid")
    lines = [
        "STAGE REVIEW (read-only)",
        f"Staged change digest: {_terminal_safe_text(stage['staged_change_digest'])}",
        f"Artifact digest: {_terminal_safe_text(stage['artifact_digest'])}",
        "Verified contents digest: "
        + _terminal_safe_text(stage["verified_contents_digest"]),
        f"Repository: {_terminal_safe_text(change['repository_id'])}",
        f"Base commit: {_terminal_safe_text(change['base_commit'])}",
        "Declared change paths:",
        *[f"  {_terminal_safe_text(path)}" for path in paths],
        "Verifier: "
        + _terminal_safe_text(verification["verifier_id"])
        + " / "
        + _terminal_safe_text(verification["verdict"]),
        "Verification digest: "
        + _terminal_safe_text(verification["verification_digest"]),
        "Verifier trust: "
        + _terminal_safe_text(preview["verifier_trust"]["status"]),
        "Verifier trust digests: "
        + _terminal_safe_text(
            json.dumps(preview["verifier_trust"], ensure_ascii=False, sort_keys=True)
        ),
        f"Approval: {_terminal_safe_text(preview['approval'])}",
        f"Publication: {_terminal_safe_text(preview['publication'])}",
        "Patch:",
        _terminal_safe_text(change["patch"]),
    ]
    rendered = "\n".join(lines)
    if len(rendered.encode("utf-8")) > MAX_PREVIEW_BYTES:
        raise StagePreviewError("stage preview: output exceeds size limit")
    return rendered


def load_stage_preview(database_path: Path | str, staged_change_digest: str) -> str:
    """Load an existing stage using SQLite read-only mode and render its preview."""
    if (
        not isinstance(staged_change_digest, str)
        or _DIGEST_PATTERN.fullmatch(staged_change_digest) is None
    ):
        raise DurableStageStoreError("durable stage store: digest is invalid")
    try:
        path = Path(database_path)
        if path.is_symlink() or not path.is_file():
            raise StagePreviewError("stage preview: database unavailable")
        with SQLiteStagedArtifactStore(path, read_only=True) as store:
            artifact = store.load(staged_change_digest)
        return render_stage_preview(artifact)
    except (DurableStageStoreError, StagePreviewError):
        raise
    except Exception:
        raise StagePreviewError("stage preview: database unavailable") from None


def load_stage_preview_text(database_path: Path | str, staged_change_digest: str) -> str:
    """Read one exact stage in SQLite read-only mode and render terminal text."""
    if (
        not isinstance(staged_change_digest, str)
        or _DIGEST_PATTERN.fullmatch(staged_change_digest) is None
    ):
        raise DurableStageStoreError("durable stage store: digest is invalid")
    try:
        path = Path(database_path)
        if path.is_symlink() or not path.is_file():
            raise StagePreviewError("stage preview: database unavailable")
        with SQLiteStagedArtifactStore(path, read_only=True) as store:
            artifact = store.load(staged_change_digest)
        return render_stage_preview_text(artifact)
    except (DurableStageStoreError, StagePreviewError):
        raise
    except Exception:
        raise StagePreviewError("stage preview: database unavailable") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Show a read-only preview for a stored stage digest."
    )
    parser.add_argument("database", help="existing local SQLite stage database")
    parser.add_argument("staged_change_digest", help="exact sha256 stage digest")
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="render machine-readable JSON (default) or a colorless terminal review",
    )
    args = parser.parse_args(argv)
    try:
        if args.format == "json":
            rendered = load_stage_preview(args.database, args.staged_change_digest)
        else:
            rendered = load_stage_preview_text(args.database, args.staged_change_digest)
    except (DurableStageStoreError, StagePreviewError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
