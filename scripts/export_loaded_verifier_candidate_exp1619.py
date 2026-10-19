#!/usr/bin/env python3
"""One fixed, opt-in export of the EXP-1619 local verifier candidate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.export_loaded_verifier_candidate_exp1580 import (  # noqa: E402
    EXP1619_IMAGE_TAG,
    run_once,
)


def main() -> int:
    return run_once(
        image_tag=EXP1619_IMAGE_TAG,
        retain_tag=True,
        dynamic_diff_ids=True,
        require_portable_manifest=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
