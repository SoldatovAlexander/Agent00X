"""Host-side verifier image identity; intentionally excluded from the image.

Keeping this pair outside the verifier's hashed runtime context prevents the
code digest from depending on its own image/code pin values.
"""

VERIFIER_RUNTIME_IMAGE_ID = (
    "sha256:f49397ccfb59beefa21161c86379e17ae754acee810cedd3fc5de4f5494d913f"
)
# EXP-1632 validated this portable manifest and OCI config digest against the
# local containerd-backed image store. This does not establish remote import.
VERIFIER_RUNTIME_CONFIG_IMAGE_ID = (
    "sha256:cb5c068a474164060b27942d764304fed521d267a0eb83fdfa530cc90bc249d9"
)
VERIFIER_RUNTIME_CODE_DIGEST = (
    "sha256:705c3803ca36374ee0ab0bef80fb4d77b3211dd60e8168a7729a3fed46c7a2c7"
)
