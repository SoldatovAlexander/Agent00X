#!/usr/bin/env python3
"""Copy one exact observer run to a new local evidence file."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.observer_copy import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
