"""Fixed target contract for the bounded BrainBooster MVP experiment.

This profile is intentionally a data-only module: it carries no transport,
credential, Worker, approval, publication, or Docker execution capability.
"""

PINNED_OWNER = "SoldatovAlexander"
PINNED_REPOSITORY = "brainbooster_full_v11"
PINNED_COMMIT = "2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e"
PINNED_TREE = "2007066217aadafd9887fb3e3069220333b4fddb"
PINNED_FILE_COUNT = 23
# app-process-snapshot-tree/v1 binds relative paths, bytes, and executable mode.
PINNED_SNAPSHOT_TREE_DIGEST = (
    "sha256:dee0211b7ee40f6f0eeefa7ee8a4b7a46ee0e52521cdefe335f398557346b9ad"
)
# Compatibility alias: snapshot claims serialize this value as `content_digest`.
PINNED_CONTENT_DIGEST = PINNED_SNAPSHOT_TREE_DIGEST
TARGET_RUNTIME_IMAGE_ID = (
    "sha256:f22c0b03d5d60c44f433935952199aeaed497b4d3fb3400933e69a144e0fc187"
)
EXPECTED_CANDIDATE_DIGEST = "sha256:6166fc4c2a73db910a064de140e71f7bfcbebe3b99846651a3c69770cce39a18"
VERIFIER_CONTEXT_MODULES = (
    "__init__.py",
    "brainbooster_target_profile.py",
    "digests.py",
    "executor.py",
    "observer_runtime.py",
    "observation_store.py",
    "pinned_snapshot.py",
    "repository_process.py",
    "sandbox.py",
    "validator.py",
    "verifier_process.py",
    "verifier_container_entrypoint.py",
)
VERIFIER_CONTEXT_SCHEMA_FILES = (
    "checkpoint.schema.json",
    "observation-event.schema.json",
)

PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS = 30
PINNED_VERIFIER_CONTAINER_TIMEOUT_SECONDS = 60
_NUMERIC_FIELDS = ("level", "correct", "wrong", "total", "time_ms")
_INVALID_CASES = (
    ("malformed", "bool"),
    ("malformed", "fractional"),
    ("malformed", "numeric-string"),
    ("sqlite-range", "above"),
    ("sqlite-range", "below"),
)
PINNED_HTTP_DB_FAILURE_CATEGORIES = frozenset(
    f"{category}-{phase}-{field}-{case}"
    for category, case in _INVALID_CASES
    for field in _NUMERIC_FIELDS
    for phase in ("status", "no-write")
)
PINNED_HTTP_DB_FIXED_FAILURE_CODES = frozenset(
    {
        "readiness-exit",
        "readiness-timeout",
        "overflow-status",
        "overflow-no-write",
        "valid-status",
        "valid-body",
        "valid-row",
    }
)
PINNED_HTTP_DB_FAILURE_CODES = frozenset(
    PINNED_HTTP_DB_FAILURE_CATEGORIES | PINNED_HTTP_DB_FIXED_FAILURE_CODES
)

PINNED_HTTP_DB_VERIFIER_PROBE = r'''import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

os.makedirs("static", exist_ok=True)
os.makedirs("frontend", exist_ok=True)
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
base = f"http://127.0.0.1:{port}"
server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port)],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

def post(payload):
    request = urllib.request.Request(
        base + "/save-session",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, response.read(4097)
    except urllib.error.HTTPError as error:
        body = error.read(4097)
        return error.code, body

def row_count():
    with sqlite3.connect("brainbooster.db", timeout=2) as connection:
        return connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

def fail(category):
    print("agent00x:test-failure:" + category, flush=True)
    raise SystemExit(1)

try:
    deadline = time.monotonic() + 5
    while True:
        if server.poll() is not None:
            fail("readiness-exit")
        try:
            with urllib.request.urlopen(base + "/openapi.json", timeout=1) as response:
                if response.status != 200:
                    fail("readiness-exit")
            break
        except (OSError, urllib.error.URLError):
            if time.monotonic() >= deadline:
                fail("readiness-timeout")
            time.sleep(0.05)

    valid = {"telegram_id": "synthetic-probe", "level": 2, "correct": 1, "wrong": 0, "total": 1, "time_ms": 250}

    def reset_rows():
        with sqlite3.connect("brainbooster.db", timeout=2) as connection:
            connection.execute("DELETE FROM sessions")

    invalid_values = (
        ("malformed", "bool", True),
        ("malformed", "fractional", 1.5),
        ("malformed", "numeric-string", "2"),
        ("sqlite-range", "above", 9223372036854775808),
        ("sqlite-range", "below", -9223372036854775809),
    )
    fields = ("level", "correct", "wrong", "total", "time_ms")
    for field in fields:
        for category, case, value in invalid_values:
            reset_rows()
            payload = dict(valid)
            payload[field] = value
            status, _body = post(json.dumps(payload, separators=(",", ":")).encode())
            if status != 422:
                fail(category + "-status-" + field + "-" + case)
            if row_count() != 0:
                fail(category + "-no-write-" + field + "-" + case)

    overflow = b'{"telegram_id":"synthetic-probe","level":1e309,"correct":1,"wrong":0,"total":1,"time_ms":250}'
    status, _body = post(overflow)
    if status != 422:
        fail("overflow-status")
    if row_count() != 0:
        fail("overflow-no-write")

    status, body = post(json.dumps(valid, separators=(",", ":")).encode())
    if status != 200:
        fail("valid-status")
    if json.loads(body) != {"status": "ok"}:
        fail("valid-body")
    with sqlite3.connect("brainbooster.db", timeout=2) as connection:
        rows = connection.execute(
            "SELECT telegram_id, level, correct, wrong, total, time_ms FROM sessions"
        ).fetchall()
    if rows != [("synthetic-probe", 2, 1, 0, 1, 250)]:
        fail("valid-row")
    print("http_db_probe=PASS invalid=25 overflow=1 valid=1")
finally:
    server.terminate()
    try:
        server.wait(timeout=3)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=2)
'''
PINNED_HTTP_DB_TEST_COMMAND = (
    "python3",
    "-c",
    PINNED_HTTP_DB_VERIFIER_PROBE.strip(),
)
