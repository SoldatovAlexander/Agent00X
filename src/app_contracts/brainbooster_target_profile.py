"""Fixed target contract for the bounded BrainBooster MVP experiment.

This profile is intentionally a data-only module: it carries no transport,
credential, Worker, approval, publication, or Docker execution capability.
"""

PINNED_OWNER = "SoldatovAlexander"
PINNED_REPOSITORY = "brainbooster_full_v11"
PINNED_COMMIT = "2c172801c27ec92e38835fbb0ddd6ab7b8fc0c0e"
PINNED_TREE = "2007066217aadafd9887fb3e3069220333b4fddb"
PINNED_FILE_COUNT = 23
PINNED_CONTENT_DIGEST = "sha256:dee0211b7ee40f6f0eeefa7ee8a4b7a46ee0e52521cdefe335f398557346b9ad"
TARGET_RUNTIME_IMAGE_ID = (
    "sha256:96cbcaf0332b6b117703aef38b77de89921778861c9c9fcb94e1df0eaa484812"
)
VERIFIER_RUNTIME_IMAGE_ID = (
    "sha256:f343041a8b7353341bc933f9bcff48a5415f585e8e642b4d22c1d0d35e22705a"
)
VERIFIER_RUNTIME_CODE_DIGEST = (
    "sha256:b1336165e906e8bd2801ff61bcc6a3740c683639416f80caea40e3e8d22825a5"
)
EXPECTED_CANDIDATE_DIGEST = "sha256:68c85e7fe084a754da791c74a169a5c6346527f6becb20fbb9fb8f56dcce34d8"
VERIFIER_CONTEXT_MODULES = (
    "__init__.py",
    "digests.py",
    "executor.py",
    "pinned_snapshot.py",
    "repository_process.py",
    "sandbox.py",
    "validator.py",
    "verifier_process.py",
    "verifier_container_entrypoint.py",
)

PINNED_HTTP_DB_TEST_TIMEOUT_SECONDS = 30
PINNED_VERIFIER_CONTAINER_TIMEOUT_SECONDS = 60

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

    fields = {"level": "x", "correct": "x", "wrong": "x", "total": "x", "time_ms": "x"}
    for field in fields:
        payload = {"telegram_id": "synthetic-probe", "level": 2, "correct": 1, "wrong": 0, "total": 1, "time_ms": 250}
        payload[field] = fields[field]
        status, _body = post(json.dumps(payload, separators=(",", ":")).encode())
        if status != 422:
            fail("malformed-status")
        if row_count() != 0:
            fail("malformed-no-write")

    overflow = b'{"telegram_id":"synthetic-probe","level":1e309,"correct":1,"wrong":0,"total":1,"time_ms":250}'
    status, _body = post(overflow)
    if status != 422:
        fail("overflow-status")
    if row_count() != 0:
        fail("overflow-no-write")

    valid = {"telegram_id": "synthetic-probe", "level": 2, "correct": 1, "wrong": 0, "total": 1, "time_ms": 250}
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
    print("http_db_probe=PASS malformed=5 overflow=1 valid=1")
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
