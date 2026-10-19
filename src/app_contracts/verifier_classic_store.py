"""Fixed OCI-manifest/config-ID bridge for the BrainBooster verifier host.

Docker's classic image store addresses a loaded OCI image by config digest,
while the signed verifier profile names the portable manifest digest. This
adapter permits only the Control Plane-reviewed EXP-1349/1350 pair. It checks
the exact config address before each invocation and never accepts a tag or a
caller-selected alias. Docker and the host remain in the trusted computing base.
"""

from __future__ import annotations

from dataclasses import replace
import subprocess
import tempfile

from .brainbooster_target_profile import PINNED_VERIFIER_CONTAINER_TIMEOUT_SECONDS
from .docker_endpoint import LOCAL_DOCKER_HOST_ARGUMENT
from .executor import VerifierInput, VerifierResult, validate_verifier_result
from .verifier_container import DockerContainerVerifier, VerifierContainerConfig
from .verifier_image_pin import (
    VERIFIER_RUNTIME_CODE_DIGEST,
    VERIFIER_RUNTIME_CONFIG_IMAGE_ID,
    VERIFIER_RUNTIME_IMAGE_ID,
)
from .verifier_process import VerifierProcessError, _collect_bounded_output


_INSPECT_FORMAT = "{{.Id}}|{{.Os}}|{{.Architecture}}"
_EXPECTED_INSPECT = (
    f"{VERIFIER_RUNTIME_CONFIG_IMAGE_ID}|linux|amd64\n".encode("ascii")
)
_CONFIG_VERIFIER_ID = (
    f"docker-image:{VERIFIER_RUNTIME_CONFIG_IMAGE_ID}"
    f"/code:{VERIFIER_RUNTIME_CODE_DIGEST}"
)
_MANIFEST_VERIFIER_ID = (
    f"docker-image:{VERIFIER_RUNTIME_IMAGE_ID}"
    f"/code:{VERIFIER_RUNTIME_CODE_DIGEST}"
)


class ClassicStoreBrainboosterVerifier:
    """Run by one fixed config ID, then report its bound manifest identity."""

    def __init__(self, docker_executable: str) -> None:
        config = VerifierContainerConfig(
            docker_executable=docker_executable,
            runtime_image_id=VERIFIER_RUNTIME_CONFIG_IMAGE_ID,
            verifier_code_digest=VERIFIER_RUNTIME_CODE_DIGEST,
            timeout_seconds=PINNED_VERIFIER_CONTAINER_TIMEOUT_SECONDS,
        )
        self._docker_executable = config.docker_executable
        self._inner = DockerContainerVerifier(config)

    def verify(self, prepared: VerifierInput) -> VerifierResult:
        if type(prepared) is not VerifierInput:
            raise VerifierProcessError("classic verifier image: request rejected")
        try:
            with tempfile.TemporaryDirectory(prefix="agent00x-image-inspect-") as config_dir:
                process = subprocess.Popen(
                    [
                        self._docker_executable,
                        LOCAL_DOCKER_HOST_ARGUMENT,
                        "image",
                        "inspect",
                        "--format",
                        _INSPECT_FORMAT,
                        VERIFIER_RUNTIME_CONFIG_IMAGE_ID,
                    ],
                    executable=self._docker_executable,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env={"DOCKER_CONFIG": config_dir},
                    shell=False,
                )
                stdout, stderr, exit_code = _collect_bounded_output(
                    process,
                    b"",
                    stdout_cap=256,
                    stderr_cap=4096,
                    timeout_seconds=15,
                )
            if (
                exit_code != 0
                or type(stdout) is not bytes
                or stdout != _EXPECTED_INSPECT
                or type(stderr) is not bytes
            ):
                raise ValueError
        except Exception:
            raise VerifierProcessError(
                "classic verifier image: exact config identity unavailable"
            ) from None

        result = self._inner.verify(prepared)
        if type(result) is not VerifierResult or result.verifier_id != _CONFIG_VERIFIER_ID:
            raise VerifierProcessError("classic verifier image: result identity rejected")
        try:
            return validate_verifier_result(
                replace(result, verifier_id=_MANIFEST_VERIFIER_ID), prepared
            )
        except Exception:
            raise VerifierProcessError(
                "classic verifier image: result binding rejected"
            ) from None


def create_brainbooster_classic_store_verifier_runner(
    docker_executable: str,
) -> ClassicStoreBrainboosterVerifier:
    """Construct the fixed adapter without invoking Docker or a subprocess."""

    return ClassicStoreBrainboosterVerifier(docker_executable)
