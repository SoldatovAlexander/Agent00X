"""Read-only, digest-bound local preview for a persisted staged artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from .durable_stage import (
    DurableStageStoreError,
    SQLiteStagedArtifactStore,
    StagedArtifact,
)

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
        seed = payload["seed"]
        verifier = payload["verifier_result"]
        preview = {
            "schema": "stage-preview/v1",
            "stage": {
                "staged_change_digest": validated.staged_change_digest,
                "artifact_digest": validated.artifact_digest,
                "verified_contents_digest": validated.verified_contents_digest,
            },
            "change": {
                "process_id": seed["process_id"],
                "repository_id": seed["repository_id"],
                "base_commit": seed["base_commit"],
                "declared_change_paths": payload["declared_change_paths"],
                "patch": payload["patch"],
            },
            "verification": {
                "verifier_id": verifier["verifier_id"],
                "verdict": verifier["verdict"],
                "verification_digest": verifier["verification_digest"],
            },
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Show a read-only preview for a stored stage digest."
    )
    parser.add_argument("database", help="existing local SQLite stage database")
    parser.add_argument("staged_change_digest", help="exact sha256 stage digest")
    args = parser.parse_args(argv)
    try:
        rendered = load_stage_preview(args.database, args.staged_change_digest)
    except (DurableStageStoreError, StagePreviewError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
