"""Deterministic synthetic Ed25519 approval keys for tests only."""

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app_contracts.approval_signature import approval_signature_payload


TEST_APPROVER_ID = "user-alice"
_TEST_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(
    bytes.fromhex("11" * 32)
)
TEST_APPROVER_PUBLIC_KEY = _TEST_PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw,
)
TEST_APPROVER_PUBLIC_KEYS = {TEST_APPROVER_ID: TEST_APPROVER_PUBLIC_KEY}


def sign_test_approval(approval: dict) -> dict:
    return sign_approval(approval, _TEST_PRIVATE_KEY)


def sign_approval(approval: dict, private_key: Ed25519PrivateKey) -> dict:
    signed = dict(approval)
    signed.pop("signature", None)
    signed["signature"] = private_key.sign(approval_signature_payload(signed)).hex()
    return signed
