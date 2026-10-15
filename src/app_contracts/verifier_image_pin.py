"""Host-side verifier image identity; intentionally excluded from the image.

Keeping this pair outside the verifier's hashed runtime context prevents the
code digest from depending on its own image/code pin values.
"""

VERIFIER_RUNTIME_IMAGE_ID = (
    "sha256:babefaa38e0e068f3af35b9f00d0ff0ea319a69e3a13697fe471b3e01a2cdf6a"
)
VERIFIER_RUNTIME_CODE_DIGEST = (
    "sha256:f63ecc2359fe0c9dcd51893d55d831bacb33daa0b289a3b87d0b6a65de1d660f"
)
