#!/usr/bin/env python3
"""Emit a deterministic, redacted structural report for a local observer DB."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from app_contracts.observer_report import (  # noqa: E402
    HistoryReportError,
    report_from_sqlite,
)


def main(argv: list[str] | None = None, *, stdout=None) -> int:
    output = sys.stdout if stdout is None else stdout
    parser = argparse.ArgumentParser(
        description="Read-only deterministic report of a local observation journal."
    )
    parser.add_argument("database", help="existing SQLite observation journal")
    parser.add_argument(
        "--artifact-database",
        help="existing read-only SQLite content-addressed artifact store",
    )
    parser.add_argument("--process-id")
    parser.add_argument("--run-id")
    parser.add_argument("--branch-id")
    parser.add_argument("--as-of-cursor", type=int)
    parser.add_argument(
        "--as-of-recorded-at",
        help="timezone-aware RFC3339 cutoff for what the journal recorded by that time",
    )
    parser.add_argument(
        "--about-occurred-at",
        help="show events that occurred by this time, including later-recorded evidence",
    )
    try:
        args = parser.parse_args(argv)
        result = report_from_sqlite(
            args.database,
            process_id=args.process_id,
            run_id=args.run_id,
            branch_id=args.branch_id,
            as_of_cursor=args.as_of_cursor,
            as_of_recorded_at=args.as_of_recorded_at,
            about_occurred_at=args.about_occurred_at,
            artifact_database=args.artifact_database,
        )
        encoded = json.dumps(
            result,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except SystemExit as exc:
        return int(exc.code or 0)
    except HistoryReportError:
        print('{"reason":"history-report-unavailable","status":"error"}', file=output)
        return 2
    print(encoded, file=output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
