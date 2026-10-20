"""Host-side verifier image identity; intentionally excluded from the image.

Keeping this pair outside the verifier's hashed runtime context prevents the
code digest from depending on its own image/code pin values.
"""

VERIFIER_RUNTIME_IMAGE_ID = (
    "sha256:228e703737010ccc001b5d784f35711ca49a00e3af4be5f0a8fcdd2fe06350a0"
)
# EXP-1658 validated this portable manifest and OCI config digest against the
# local containerd-backed image store. This does not establish remote import.
VERIFIER_RUNTIME_CONFIG_IMAGE_ID = (
    "sha256:d65ca82a1d944f76b7c86163f4f3bcd0c4b4e3c603ce5005e510fcb86ee73c42"
)
VERIFIER_RUNTIME_CODE_DIGEST = (
    "sha256:36f4f81cd98355665992fd9feb0f8ac4f3a6807b2ffb1b332956b694e9031d5f"
)
