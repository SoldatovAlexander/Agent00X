#!/usr/bin/env python3
"""Reconcile one existing signed-stage GitHub journal using GET-only access."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.signed_github_reconciliation import main


if __name__ == "__main__":
    raise SystemExit(main())
