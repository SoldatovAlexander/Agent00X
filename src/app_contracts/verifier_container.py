"""Fixed-profile Docker adapter for the local verifier prototype.

The Docker Engine, host kernel, launcher configuration and pinned image remain
in the prototype's trusted computing base. This adapter does not attest them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
import secrets
import subprocess
import tempfile
import uuid

from .executor import VerifierInput, VerifierResult, validate_verifier_result
from .docker_endpoint import LOCAL_DOCKER_HOST_ARGUMENT
from .verifier_process import (
    VerifierProcessConfig,
    VerifierProcessError,
    VerifierProcessRequest,
    _collect_bounded_output,
    _quietly_reap,
    bind_verifier_response,
    run_verifier_command,
)


VERIFIER_BASE_IMAGE = (
    "python:3.11.16-slim@sha256:"
    "174bec68e0451bffabbb08c7d5d21c6b253f772d81d52b9558af97bb3159b761"
)
MAX_CONTAINER_TIMEOUT_SECONDS = 3_600
DEFAULT_CONTAINER_TIMEOUT_SECONDS = 900
MAX_CONTAINER_OUTPUT_BYTES = 256_000
_IMAGE_ID_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")

_DOCKER_ARGS = (
    "run",
    "--rm",
    "--interactive",
    "--pull=never",
    "--network=none",
    "--platform=linux/amd64",
    "--read-only",
    "--user=65532:65532",
    "--cap-drop=ALL",
    "--security-opt=no-new-privileges:true",
    "--pids-limit=64",
    "--memory=256m",
    "--cpus=1.0",
    "--tmpfs",
    "/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777,uid=65532,gid=65532",
    "--tmpfs",
    "/work:rw,noexec,nosuid,nodev,size=32m,mode=0700,uid=65532,gid=65532",
    "--workdir=/work",
)
# The runtime image fixes its own ENTRYPOINT to the verifier module, so the
# only argument the launcher ever appends is the per-invocation nonce. The
# child echoes it in the bounded verifier_id result field; the parent requires
# an exact match before any result binding is accepted. The nonce only rejects
# accidental/stale response replay: it does not attest the child, protect a
# malicious child that sees its nonce, or authenticate Docker/host/kernel.
_CONTAINER_ENTRYPOINT_ARGUMENT = "--invocation-nonce="
_INVOCATION_NONCE_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
# Shape-only placeholder for fixed-argv validation; never used in a real run.
_SAMPLE_INVOCATION_NONCE = "0" * 64


def _validate_invocation_nonce(value: object) -> str:
    if type(value) is not str or _INVOCATION_NONCE_PATTERN.fullmatch(value) is None:
        raise VerifierProcessError("verifier container: invocation nonce is invalid")
    return value


def _new_invocation_nonce() -> str:
    """Generate one fresh 256-bit cryptographic nonce for a single invocation."""

    return secrets.token_hex(32)


@dataclass(frozen=True)
class VerifierContainerConfig:
    """Trusted launcher settings; none are read from a verifier request."""

    docker_executable: str
    runtime_image_id: str
    verifier_code_digest: str
    timeout_seconds: int = DEFAULT_CONTAINER_TIMEOUT_SECONDS
    max_stdout_bytes: int = MAX_CONTAINER_OUTPUT_BYTES
    max_stderr_bytes: int = MAX_CONTAINER_OUTPUT_BYTES

    def __post_init__(self) -> None:
        if (
            type(self.runtime_image_id) is not str
            or _IMAGE_ID_PATTERN.fullmatch(self.runtime_image_id) is None
        ):
            raise VerifierProcessError("verifier container: image identity is invalid")
        if (
            type(self.verifier_code_digest) is not str
            or _IMAGE_ID_PATTERN.fullmatch(self.verifier_code_digest) is None
        ):
            raise VerifierProcessError("verifier container: code identity is invalid")
        if (
            type(self.max_stdout_bytes) is not int
            or type(self.max_stderr_bytes) is not int
            or self.max_stdout_bytes > MAX_CONTAINER_OUTPUT_BYTES
            or self.max_stderr_bytes > MAX_CONTAINER_OUTPUT_BYTES
        ):
            raise VerifierProcessError("verifier container: output limits are invalid")
        # Reuse the existing strict executable, argv and resource validation.
        VerifierProcessConfig(
            executable=self.docker_executable,
            argv=(
                self.docker_executable,
                LOCAL_DOCKER_HOST_ARGUMENT,
                *_DOCKER_ARGS,
                self.runtime_image_id,
                f"{_CONTAINER_ENTRYPOINT_ARGUMENT}{_SAMPLE_INVOCATION_NONCE}",
            ),
            timeout_seconds=self.timeout_seconds,
            max_stdout_bytes=self.max_stdout_bytes,
            max_stderr_bytes=self.max_stderr_bytes,
        )
        if self.timeout_seconds > MAX_CONTAINER_TIMEOUT_SECONDS:
            raise VerifierProcessError("verifier container: timeout is invalid")

    def command_config(
        self, container_name: str, invocation_nonce: str
    ) -> VerifierProcessConfig:
        """Return fixed Docker argv with a per-call name and invocation nonce."""

        _validate_invocation_nonce(invocation_nonce)
        return VerifierProcessConfig(
            executable=self.docker_executable,
            argv=(
                self.docker_executable,
                LOCAL_DOCKER_HOST_ARGUMENT,
                *_DOCKER_ARGS[:2],
                f"--name={container_name}",
                *_DOCKER_ARGS[2:],
                self.runtime_image_id,
                f"{_CONTAINER_ENTRYPOINT_ARGUMENT}{invocation_nonce}",
            ),
            timeout_seconds=self.timeout_seconds,
            max_stdout_bytes=self.max_stdout_bytes,
            max_stderr_bytes=self.max_stderr_bytes,
        )


class DockerContainerVerifier:
    """Invoke exactly one fixed-profile container for one bounded request."""

    def __init__(self, config: object) -> None:
        if type(config) is not VerifierContainerConfig:
            raise VerifierProcessError("verifier container: config is invalid")
        self._config = config

    def verify(self, prepared: VerifierInput) -> VerifierResult:
        if type(prepared) is not VerifierInput:
            raise VerifierProcessError("verifier container: request shape is invalid")
        if prepared.test_timeout_seconds + 5 > self._config.timeout_seconds:
            raise VerifierProcessError("verifier container: timeout is invalid")
        request = VerifierProcessRequest.from_verifier_input(prepared)
        container_name = f"agent00x-verifier-{uuid.uuid4().hex}"
        invocation_nonce = _new_invocation_nonce()
        with tempfile.TemporaryDirectory(prefix="agent00x-docker-config-") as config_dir:
            child_environ = {"DOCKER_CONFIG": config_dir}
            try:
                response = run_verifier_command(
                    self._config.command_config(container_name, invocation_nonce),
                    request,
                    environ=child_environ,
                )
                if response.verifier_result.verifier_id != invocation_nonce:
                    raise VerifierProcessError(
                        "verifier container: invocation nonce mismatch"
                    )
                bound_result = bind_verifier_response(request, response)
                trusted_identity = (
                    f"docker-image:{self._config.runtime_image_id}"
                    f"/code:{self._config.verifier_code_digest}"
                )
                trusted_result = replace(
                    bound_result, verifier_id=trusted_identity
                )
                return validate_verifier_result(trusted_result, prepared)
            except Exception:
                self._best_effort_cleanup(container_name, child_environ)
                raise

    def _best_effort_cleanup(
        self, container_name: str, child_environ: dict[str, str]
    ) -> None:
        """Force-remove a possibly detached run after any failed invocation."""

        process = None
        try:
            argv = (
                self._config.docker_executable,
                LOCAL_DOCKER_HOST_ARGUMENT,
                "rm",
                "--force",
                container_name,
            )
            process = subprocess.Popen(
                list(argv),
                executable=self._config.docker_executable,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=dict(child_environ),
                shell=False,
            )
            _collect_bounded_output(
                process,
                b"",
                stdout_cap=4_096,
                stderr_cap=4_096,
                timeout_seconds=5,
            )
        except Exception:
            if process is not None:
                _quietly_reap(process)
