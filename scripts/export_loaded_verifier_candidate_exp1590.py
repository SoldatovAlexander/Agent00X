#!/usr/bin/env python3
"""Run the bounded loaded-export route once under EXP-1590's unique tag."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.export_loaded_verifier_candidate_exp1580 import (  # noqa: E402
    EXP1590_IMAGE_TAG,
    run_once,
)


def main() -> int:
    return run_once(image_tag=EXP1590_IMAGE_TAG)


if __name__ == "__main__":
    raise SystemExit(main())
