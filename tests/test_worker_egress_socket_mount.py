"""Opt-in probe for a synthetic host socket mounted into an isolated container."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import uuid
import unittest

from app_contracts.brainbooster_target_profile import TARGET_RUNTIME_IMAGE_ID


SOCKET_DIRECTORY_DESTINATION = "/run/agent00x"
SOCKET_DESTINATION = f"{SOCKET_DIRECTORY_DESTINATION}/broker.sock"
CONTAINER_USER = f"{os.getuid()}:{os.getgid()}"
CONTAINER_PYTHON = (
    "import socket; s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); "
    "s.settimeout(5); s.connect('/run/agent00x-broker.sock'); "
    "s.sendall(b'ping'); reply=s.recv(4); s.close(); "
    "raise SystemExit(0 if reply == b'pong' else 9)"
)
IP_EGRESS_PROBE = (
    "import socket; s=socket.socket(); s.settimeout(1); "
    "\ntry: s.connect(('1.1.1.1',53))\n"
    "except OSError: print('blocked')\n"
    "else: raise SystemExit(8)\nfinally: s.close()"
)
DNS_EGRESS_PROBE = (
    "import socket,signal; signal.alarm(4)\n"
    "try: socket.getaddrinfo('api.github.com',443)\n"
    "except (OSError,InterruptedError): print('blocked')\n"
    "else: raise SystemExit(8)\nfinally: signal.alarm(0)"
)


def _classify_docker_start_failure(stderr: object) -> str:
    """Map private Docker diagnostics to a fixed, non-sensitive category."""
    if type(stderr) is not str:
        return "diagnostic-unavailable"
    diagnostic = stderr.lower()
    if any(
        marker in diagnostic
        for marker in ("cannot connect to the docker daemon", "is the docker daemon running")
    ):
        return "daemon-unavailable"
    if any(
        marker in diagnostic
        for marker in (
            "mounts denied",
            "not shared from the host",
            "operation not permitted",
            "permission denied",
            "invalid mount config",
            "not a directory",
        )
    ):
        return "socket-mount-denied-or-unsupported"
    if any(
        marker in diagnostic
        for marker in ("no such image", "image not known", "pull access denied")
    ):
        return "image-unavailable"
    if any(
        marker in diagnostic
        for marker in ("unknown flag", "invalid argument", "unsupported")
    ):
        return "runtime-option-unsupported"
    return "unknown-start-failure"


class DockerFailureClassificationTests(unittest.TestCase):
    def test_failure_classifier_returns_only_fixed_categories(self):
        cases = (
            ("Cannot connect to the Docker daemon at /private/path", "daemon-unavailable"),
            ("Mounts denied: /private/socket is not shared from the host", "socket-mount-denied-or-unsupported"),
            ("No such image: sha256:synthetic", "image-unavailable"),
            ("unknown flag: --synthetic", "runtime-option-unsupported"),
            ("synthetic unclassified diagnostic marker", "unknown-start-failure"),
            (None, "diagnostic-unavailable"),
        )
        for diagnostic, expected in cases:
            with self.subTest(expected=expected):
                category = _classify_docker_start_failure(diagnostic)
                self.assertEqual(category, expected)
                self.assertRegex(category, r"^[a-z-]+$")
                self.assertNotIn(str(diagnostic), category)


@unittest.skipUnless(
    os.environ.get("RUN_DOCKER_SANDBOX_TESTS") == "1",
    "Docker socket-mount probe is opt-in",
)
class WorkerEgressSocketMountTests(unittest.TestCase):
    def test_network_none_container_can_reach_only_synthetic_host_socket(self):
        docker = os.environ.get("AGENT00X_DOCKER_EXECUTABLE") or shutil.which("docker")
        self.assertIsInstance(docker, str, "Docker executable unavailable")
        self.assertTrue(Path(docker).is_absolute(), "Docker executable must be absolute")

        try:
            image = subprocess.run(
                [docker, "image", "inspect", "--format={{.Id}}", TARGET_RUNTIME_IMAGE_ID],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except Exception:
            self.fail("pinned target image preflight failed")
        self.assertEqual(image.returncode, 0, "pinned target image unavailable")
        self.assertEqual(image.stdout.strip(), TARGET_RUNTIME_IMAGE_ID)

        container_id: str | None = None
        container_name: str | None = None
        broker = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_errors: list[BaseException] = []
        server_thread: threading.Thread | None = None
        try:
            with tempfile.TemporaryDirectory(prefix="agent00x-uds-probe-") as tmp:
                runtime_dir = Path(tmp)
                runtime_dir.chmod(0o700)
                socket_path = runtime_dir / "broker.sock"
                broker.bind(str(socket_path))
                socket_path.chmod(0o600)
                broker.listen(1)
                broker.settimeout(12)

                def serve_one_fixed_exchange() -> None:
                    try:
                        connection, _address = broker.accept()
                        with connection:
                            connection.settimeout(5)
                            if connection.recv(4) != b"ping":
                                raise ValueError
                            connection.sendall(b"pong")
                    except BaseException as exc:
                        server_errors.append(exc)

                server_thread = threading.Thread(
                    target=serve_one_fixed_exchange,
                    name="agent00x-synthetic-uds-broker",
                    daemon=True,
                )
                server_thread.start()
                container_name = f"agent00x-exp760-{uuid.uuid4().hex}"

                try:
                    start = subprocess.run(
                        [
                            docker,
                            "run",
                            "--detach",
                            "--rm",
                            "--network",
                            "none",
                            "--read-only",
                            "--cap-drop",
                            "ALL",
                            "--security-opt",
                            "no-new-privileges",
                            "--user",
                            CONTAINER_USER,
                            "--pids-limit",
                            "16",
                            "--memory",
                            "256m",
                            "--cpus",
                            "0.5",
                            "--name",
                            container_name,
                            "--tmpfs",
                            "/tmp:rw,noexec,nosuid,size=4m",
                            "--mount",
                            f"type=bind,src={runtime_dir},dst=/run/agent00x,readonly",
                            TARGET_RUNTIME_IMAGE_ID,
                            "python3",
                            "-c",
                            "import time; time.sleep(60)",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=20,
                        check=False,
                    )
                except Exception:
                    self.fail("pinned socket-mount container start failed")
                if start.returncode != 0:
                    category = _classify_docker_start_failure(
                        getattr(start, "stderr", "")
                    )
                    self.fail(
                        "pinned socket-mount container start failed "
                        f"(exit={start.returncode}, category={category})"
                    )
                candidate_id = start.stdout.strip()
                self.assertTrue(
                    re.fullmatch(r"[0-9a-f]{12,64}", candidate_id),
                    "container identity unavailable",
                )
                container_id = candidate_id

                try:
                    inspect = subprocess.run(
                        [docker, "inspect", "--format={{json .}}", container_id],
                        capture_output=True,
                        text=True,
                        timeout=15,
                        check=False,
                    )
                except Exception:
                    self.fail("container security inspection failed")
                self.assertEqual(inspect.returncode, 0, "container security inspection failed")
                try:
                    details = json.loads(inspect.stdout)
                    if type(details) is not dict:
                        raise ValueError
                    host_config = details["HostConfig"]
                    config = details["Config"]
                    mounts = details["Mounts"]
                except Exception:
                    self.fail("container security inspection was malformed")
                self.assertEqual(host_config.get("NetworkMode"), "none")
                self.assertIs(host_config.get("ReadonlyRootfs"), True)
                self.assertIn("ALL", host_config.get("CapDrop", []))
                self.assertTrue(
                    any("no-new-privileges" in item for item in host_config.get("SecurityOpt", []))
                )
                self.assertEqual(config.get("User"), CONTAINER_USER)
                self.assertEqual(host_config.get("PidsLimit"), 16)
                self.assertEqual(host_config.get("Memory"), 256 * 1024 * 1024)
                self.assertEqual(host_config.get("NanoCpus"), 500_000_000)
                bind_mounts = [mount for mount in mounts if mount.get("Type") == "bind"]
                self.assertEqual(len(bind_mounts), 1)
                self.assertEqual(
                    bind_mounts[0].get("Destination"), SOCKET_DIRECTORY_DESTINATION
                )
                self.assertEqual(bind_mounts[0].get("Source"), str(runtime_dir))
                self.assertIs(bind_mounts[0].get("RW"), False)

                try:
                    exchange = subprocess.run(
                        [docker, "exec", container_id, "python3", "-c", CONTAINER_PYTHON],
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                except Exception:
                    self.fail("synthetic socket exchange failed")
                self.assertEqual(exchange.returncode, 0, "synthetic socket exchange failed")

                for probe in (IP_EGRESS_PROBE, DNS_EGRESS_PROBE):
                    try:
                        network = subprocess.run(
                            [docker, "exec", container_id, "python3", "-c", probe],
                            capture_output=True,
                            text=True,
                            timeout=8,
                            check=False,
                        )
                    except Exception:
                        self.fail("network-none probe did not complete")
                    self.assertEqual(network.returncode, 0, "network-none probe failed")
                    self.assertEqual(network.stdout.strip(), "blocked")

                server_thread.join(timeout=2)
                self.assertFalse(server_thread.is_alive(), "synthetic broker did not stop")
                self.assertFalse(server_errors, "synthetic broker exchange failed")
        finally:
            cleanup_returncode: int | None = None
            cleanup_failed = False
            if container_name is not None:
                try:
                    cleanup = subprocess.run(
                        [docker, "rm", "--force", container_name],
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                except Exception:
                    cleanup_failed = True
                else:
                    cleanup_returncode = cleanup.returncode
            cleanup_unconfirmed = container_id is not None and (
                cleanup_failed or cleanup_returncode != 0
            )
            broker.close()
            if server_thread is not None:
                server_thread.join(timeout=2)
            if cleanup_unconfirmed:
                self.fail("container cleanup failed (status unavailable or nonzero)")


if __name__ == "__main__":
    unittest.main()
