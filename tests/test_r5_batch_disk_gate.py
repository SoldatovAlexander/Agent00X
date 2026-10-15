from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.run_r5_batch_cli import (
    MIN_R5_DISK_FREE_BYTES,
    R5BatchCLIError,
    R5OutputPaths,
    _require_disk_headroom,
)


class R5BatchDiskGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.paths = R5OutputPaths(
            root / "ledger.sqlite3",
            root / "stage.sqlite3",
            root / "observer.sqlite3",
        )

    def test_accepts_exact_minimum_and_reports_available_bytes(self):
        self.assertEqual(
            _require_disk_headroom(
                self.paths,
                lambda _path: SimpleNamespace(free=MIN_R5_DISK_FREE_BYTES),
            ),
            MIN_R5_DISK_FREE_BYTES,
        )

    def test_rejects_less_than_minimum_without_creating_destinations(self):
        with self.assertRaisesRegex(R5BatchCLIError, "disk headroom unavailable"):
            _require_disk_headroom(
                self.paths,
                lambda _path: SimpleNamespace(free=MIN_R5_DISK_FREE_BYTES - 1),
            )
        self.assertTrue(all(not path.exists() for path in (
            self.paths.ledger, self.paths.stage, self.paths.observer
        )))

    def test_rejects_destinations_on_different_devices_before_disk_probe(self):
        other = Path(self.temporary.name) / "other"
        other.mkdir()
        paths = R5OutputPaths(
            self.paths.ledger,
            other / "stage.sqlite3",
            self.paths.observer,
        )
        real_stat = Path.stat

        def fake_stat(path, *args, **kwargs):
            info = real_stat(path, *args, **kwargs)
            if path == other.resolve():
                return SimpleNamespace(st_dev=info.st_dev + 1)
            return info

        probes = []
        with patch.object(Path, "stat", fake_stat):
            with self.assertRaisesRegex(R5BatchCLIError, "disk headroom unavailable"):
                _require_disk_headroom(paths, lambda path: probes.append(path))
        self.assertEqual(probes, [])

    def test_rejects_missing_parent_before_disk_probe(self):
        missing = Path(self.temporary.name) / "missing"
        paths = R5OutputPaths(
            missing / "ledger.sqlite3",
            missing / "stage.sqlite3",
            missing / "observer.sqlite3",
        )
        probes = []
        with self.assertRaisesRegex(R5BatchCLIError, "disk headroom unavailable"):
            _require_disk_headroom(paths, lambda path: probes.append(path))
        self.assertEqual(probes, [])


if __name__ == "__main__":
    unittest.main()
