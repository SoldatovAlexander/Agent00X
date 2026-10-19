#!/usr/bin/env python3
"""Report bounded public verifier bootstrap facts; never grant host trust."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.verifier_bootstrap_preflight import (  # noqa: E402
    MAX_BOOTSTRAP_BYTES,
    parse_pinned_public_verifier_bootstrap,
)


_FAILURE = "verifier bootstrap preflight: public input rejected\n"


def _read_exact_public_file(value: str) -> bytes:
    descriptor = None
    try:
        path = Path(value)
        if not path.is_absolute() or path.is_symlink():
            raise ValueError
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= MAX_BOOTSTRAP_BYTES:
            raise ValueError
        no_follow = getattr(os, "O_NOFOLLOW", None)
        no_block = getattr(os, "O_NONBLOCK", None)
        if type(no_follow) is not int or no_follow <= 0 or type(no_block) is not int:
            raise ValueError
        descriptor = os.open(
            path, os.O_RDONLY | no_follow | no_block | getattr(os, "O_CLOEXEC", 0)
        )
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
            or opened.st_size != before.st_size
        ):
            raise ValueError
        raw = os.read(descriptor, MAX_BOOTSTRAP_BYTES + 1)
        if len(raw) != opened.st_size:
            raise ValueError
        return raw
    except Exception:
        raise ValueError(_FAILURE) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def main(argv: list[str] | None = None, *, stdout=None, stderr=None) -> int:
    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bootstrap", help="absolute path to one public bootstrap line")
    parser.add_argument("--expected-sha256", required=True, help="caller-pinned exact file digest")
    args = parser.parse_args(argv)
    try:
        raw = _read_exact_public_file(args.bootstrap)
        bound = parse_pinned_public_verifier_bootstrap(
            raw, expected_sha256=args.expected_sha256
        )
    except Exception:
        errors.write(_FAILURE)
        return 2
    output.write(
        "BOOTSTRAP_PIN_CONFIRMED"
        f"|port={bound.connect_port}"
        f"|ca={bound.tls_ca_sha256}"
        f"|signer={bound.verifier_public_key_sha256}"
        "|trust=unestablished\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
