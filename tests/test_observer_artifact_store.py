from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.digests import canonical_json
from app_contracts.observer_artifact_store import (
    MAX_ARTIFACT_BYTES,
    ObserverArtifactStoreError,
    SQLiteObserverArtifactStore,
)


class SQLiteObserverArtifactStoreTests(unittest.TestCase):
    def test_content_addressed_insert_is_immutable_and_resolves_metadata_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "artifacts.sqlite3"
            payload = canonical_json({"fixture": "synthetic", "value": 7})
            with SQLiteObserverArtifactStore(database) as store:
                first = store.put_json(
                    payload, classification="internal", redaction_status="complete"
                )
                second = store.put_json(
                    payload, classification="internal", redaction_status="complete"
                )
                self.assertEqual(first, second)
                self.assertEqual(store.read_json(first.artifact_ref), payload)
                self.assertEqual(store.resolve(first.artifact_ref), first)
                self.assertNotIn(payload.decode(), repr(first) + repr(store))
                with self.assertRaisesRegex(
                    ObserverArtifactStoreError, "write policy refused"
                ):
                    store.put_json(
                        payload, classification="public", redaction_status="complete"
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    store._connection.execute(
                        "UPDATE observer_artifacts SET content_bytes = 0 WHERE artifact_ref = ?",
                        (first.artifact_ref,),
                    )

            with SQLiteObserverArtifactStore(database, read_only=True) as reader:
                self.assertEqual(reader.resolve(first.artifact_ref), first)
                with self.assertRaisesRegex(
                    ObserverArtifactStoreError, "write policy refused"
                ):
                    reader.put_json(
                        payload, classification="internal", redaction_status="complete"
                    )

    def test_bad_write_policy_credentials_size_and_reference_fail_safely(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "artifacts.sqlite3"
            with SQLiteObserverArtifactStore(database) as store:
                payload = canonical_json({"fixture": "synthetic"})
                for classification, redaction_status in (
                    ("confidential", "complete"),
                    ("internal", "redacted"),
                    ([], "complete"),
                ):
                    with self.subTest(classification=type(classification).__name__):
                        with self.assertRaises(ObserverArtifactStoreError):
                            store.put_json(
                                payload,
                                classification=classification,
                                redaction_status=redaction_status,
                            )

                secret_shaped = canonical_json(
                    {"api_key": "SYNTHETIC_NOT_A_CREDENTIAL_123456789"}
                )
                with self.assertRaisesRegex(
                    ObserverArtifactStoreError, "content rejected"
                ):
                    store.put_json(
                        secret_shaped,
                        classification="internal",
                        redaction_status="complete",
                    )
                with self.assertRaisesRegex(
                    ObserverArtifactStoreError, "content rejected"
                ):
                    store.put_json(
                        b"x" * (MAX_ARTIFACT_BYTES + 1),
                        classification="internal",
                        redaction_status="complete",
                    )
                with self.assertRaisesRegex(
                    ObserverArtifactStoreError, "reference unavailable"
                ):
                    store.read_json("artifact://../../not-content-addressed")
                with self.assertRaisesRegex(
                    ObserverArtifactStoreError, "reference unavailable"
                ) as raised:
                    store.read_json("artifact://sha256/" + "0" * 64)
                self.assertNotIn("SYNTHETIC_NOT_A_CREDENTIAL", str(raised.exception))

    def test_store_rejects_tampered_content_and_malformed_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "artifacts.sqlite3"
            payload = canonical_json({"fixture": "tamper-control"})
            with SQLiteObserverArtifactStore(database) as store:
                record = store.put_json(
                    payload, classification="public", redaction_status="complete"
                )
                store._connection.execute("DROP TRIGGER observer_artifacts_no_update")
                store._connection.execute(
                    "UPDATE observer_artifacts SET content_json = ? WHERE artifact_ref = ?",
                    (canonical_json({"fixture": "changed"}), record.artifact_ref),
                )
                with self.assertRaisesRegex(
                    ObserverArtifactStoreError, "reference unavailable"
                ):
                    store.resolve(record.artifact_ref)

            with self.assertRaisesRegex(
                ObserverArtifactStoreError, "database unavailable"
            ):
                SQLiteObserverArtifactStore(database)

            malformed = Path(temporary) / "malformed.sqlite3"
            with closing(sqlite3.connect(malformed)) as connection, connection:
                connection.execute("CREATE TABLE unrelated (value TEXT)")
            with self.assertRaisesRegex(
                ObserverArtifactStoreError, "database unavailable"
            ):
                SQLiteObserverArtifactStore(malformed, read_only=True)

    def test_noncanonical_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "artifacts.sqlite3"
            with SQLiteObserverArtifactStore(database) as store:
                with self.assertRaisesRegex(
                    ObserverArtifactStoreError, "content rejected"
                ):
                    store.put_json(
                        json.dumps({"b": 1, "a": 2}).encode(),
                        classification="internal",
                        redaction_status="complete",
                    )


if __name__ == "__main__":
    unittest.main()
