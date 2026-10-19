#!/usr/bin/env python3
"""Run the bounded loaded-export route once under EXP-1586's unique tag."""

from __future__ import annotations

from scripts.export_loaded_verifier_candidate_exp1580 import (
    EXP1586_IMAGE_TAG,
    run_once,
)


def main() -> int:
    return run_once(image_tag=EXP1586_IMAGE_TAG)


if __name__ == "__main__":
    raise SystemExit(main())
