#!/usr/bin/env python3
"""Create a quiescent, exact-digest snapshot of a SQLite WAL stage."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.wal_stage_snapshot import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
