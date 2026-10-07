#!/usr/bin/env python3
"""Run the signed-stage operator flow against an in-memory mock only."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.signed_mock_publication import main


if __name__ == "__main__":
    raise SystemExit(main())
