"""Host-side verifier image identity; intentionally excluded from the image.

Keeping this pair outside the verifier's hashed runtime context prevents the
code digest from depending on its own image/code pin values.
"""

VERIFIER_RUNTIME_IMAGE_ID = (
    "sha256:a68ce6da5d5884809d7db627868ec168c4618badf3ebbf709f5d672fcfdca8ad"
)
# EXP-1682 validated this portable manifest and config digest from the current
# local verifier context; EXP-1683 confirmed the exact local tag tuple. This
# does not establish remote import or deployment.
VERIFIER_RUNTIME_CONFIG_IMAGE_ID = (
    "sha256:bbae0284355b7b3937a07f5a20ed7d003686aac09a1438bf0a57274bc6aa9469"
)
VERIFIER_RUNTIME_CODE_DIGEST = (
    "sha256:36f4f81cd98355665992fd9feb0f8ac4f3a6807b2ffb1b332956b694e9031d5f"
)
