#!/usr/bin/env python3
"""Build/load/save one offline verifier candidate for the EXP-1658 fix."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import export_loaded_verifier_candidate_exp1580 as candidate


def main() -> int:
    return candidate.run_once(
        image_tag=candidate.EXP1658_IMAGE_TAG,
        retain_tag=True,
        dynamic_diff_ids=True,
        require_portable_manifest=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
