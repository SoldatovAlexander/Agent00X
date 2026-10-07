#!/usr/bin/env python3
"""Publish one exact signed stage to the fixed GitHub App target."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.signed_github_publication import main


if __name__ == "__main__":
    raise SystemExit(main())
