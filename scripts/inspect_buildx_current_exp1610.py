#!/usr/bin/env python3
"""One fixed, opt-in inspect of the selected local Buildx builder (EXP-1610)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.inspect_buildx_default_exp1609 import run_once  # noqa: E402


def main() -> int:
    return run_once(builder_name=None)


if __name__ == "__main__":
    raise SystemExit(main())
