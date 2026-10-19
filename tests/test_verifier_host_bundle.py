from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import build_verifier_host_bundle as bundle_builder
import stream_pinned_verifier_host_bundle as transfer
from app_contracts.brainbooster_target_profile import PINNED_HTTP_DB_FAILURE_CODES

_EXPECTED_VERIFIER_HOST_PINS = frozenset({
    "cryptography==50.0.2",
    "cffi==2.1.1",
    "pycparser==2.22",
    "certifi==2026.7.22",
})


class VerifierHostBundleTests(unittest.TestCase):
    def test_observation_schema_failure_code_enum_matches_fixed_probe_codes(self):
        schema = json.loads(
            (ROOT / "schemas/observation-event.schema.json").read_text()
        )
        enum = schema["properties"]["safe_parameters"]["properties"][
            "sandbox_failure_code"
        ]["enum"]
        self.assertEqual(len(enum), 57)
        self.assertEqual(set(enum), PINNED_HTTP_DB_FAILURE_CODES)

    def _make_project(self, root: Path) -> None:
        files = {
            "scripts/serve_ephemeral_signed_verifier_https.py": b"print('host')\n",
            "requirements-verifier-host.txt": b"cryptography==50.0.2\n",
            "src/app_contracts/__init__.py": b"",
            "src/app_contracts/signed_verifier_http_service.py": (
                b"from .signed_verifier_service import SERVICE\n"
            ),
            "src/app_contracts/signed_verifier_service.py": (
                b"from .nested.profile import PROFILE\nSERVICE = PROFILE\n"
            ),
            "src/app_contracts/nested/__init__.py": b"",
            "src/app_contracts/nested/profile.py": b"PROFILE = 'fixed'\n",
            "src/app_contracts/service.py": b"SERVICE = 1\n",
            "schemas/checkpoint.schema.json": b'{"title":"checkpoint"}\n',
            "schemas/observation-event.schema.json": b'{"title":"event"}\n',
            "tests/should_not_ship.py": b"test fixture\n",
            "scripts/unrelated.py": b"unrelated\n",
            ".env": b"must not ship\n",
            ".env.production": b"synthetic placeholder\n",
            "id_ed25519": b"synthetic private-key placeholder\n",
            "credentials/AGENT_VERIFIER_SIGNING_SEED": b"synthetic seed placeholder\n",
            "secrets/verifier-signing-key.pem": b"synthetic PEM placeholder\n",
        }
        for name, data in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def _archive_members(self, archive_bytes: bytes) -> dict[str, bytes]:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
            return {
                item.name: archive.extractfile(item).read()
                for item in archive.getmembers()
                if item.isfile()
            }

    def test_bundle_is_byte_stable_across_mtime_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_project(root)
            first = bundle_builder.build_bundle(root)
            for path in root.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    os.utime(path, (1_700_000_000, 1_700_000_000))
            second = bundle_builder.build_bundle(root)

        self.assertEqual(first, second)
        archive_bytes, digest, member_count, source_bytes = first
        self.assertEqual(hashlib.sha256(archive_bytes).hexdigest(), digest)
        self.assertEqual(member_count, 9)
        self.assertEqual(source_bytes, sum(
            len(data)
            for name, data in {
                "scripts/serve_ephemeral_signed_verifier_https.py": b"print('host')\n",
                "requirements-verifier-host.txt": b"cryptography==50.0.2\n",
                "src/app_contracts/__init__.py": b"",
                "src/app_contracts/signed_verifier_http_service.py": (
                    b"from .signed_verifier_service import SERVICE\n"
                ),
                "src/app_contracts/signed_verifier_service.py": (
                    b"from .nested.profile import PROFILE\nSERVICE = PROFILE\n"
                ),
                "src/app_contracts/nested/__init__.py": b"",
                "src/app_contracts/nested/profile.py": b"PROFILE = 'fixed'\n",
                "schemas/checkpoint.schema.json": b'{"title":"checkpoint"}\n',
                "schemas/observation-event.schema.json": b'{"title":"event"}\n',
            }.items()
        ))

    def test_archive_has_fixed_allowlist_and_canonical_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_project(root)
            archive_bytes, digest, member_count, source_bytes = bundle_builder.build_bundle(root)

        members = self._archive_members(archive_bytes)
        source_names = sorted(name for name in members if name != "MANIFEST.json")
        self.assertEqual(source_names, [
            "requirements-verifier-host.txt",
            "schemas/checkpoint.schema.json",
            "schemas/observation-event.schema.json",
            "scripts/serve_ephemeral_signed_verifier_https.py",
            "src/app_contracts/__init__.py",
            "src/app_contracts/nested/__init__.py",
            "src/app_contracts/nested/profile.py",
            "src/app_contracts/signed_verifier_http_service.py",
            "src/app_contracts/signed_verifier_service.py",
        ])
        self.assertNotIn("src/app_contracts/service.py", members)
        self.assertNotIn("src/app_contracts/unused.py", members)
        self.assertNotIn("tests/should_not_ship.py", members)
        self.assertNotIn("scripts/unrelated.py", members)
        self.assertNotIn(".env", members)
        self.assertNotIn(".env.production", members)
        self.assertNotIn("id_ed25519", members)
        self.assertNotIn("credentials/AGENT_VERIFIER_SIGNING_SEED", members)
        self.assertNotIn("secrets/verifier-signing-key.pem", members)
        self.assertEqual(members["requirements-verifier-host.txt"], b"cryptography==50.0.2\n")
        manifest_bytes = members["MANIFEST.json"]
        self.assertEqual(
            manifest_bytes,
            json.dumps(
                json.loads(manifest_bytes),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii") + b"\n",
        )
        manifest = json.loads(manifest_bytes)
        self.assertEqual(
            [entry["path"] for entry in manifest["files"]], source_names
        )
        for entry in manifest["files"]:
            self.assertEqual(
                entry["sha256"], hashlib.sha256(members[entry["path"]]).hexdigest()
            )
        self.assertEqual(member_count, len(source_names))
        self.assertEqual(source_bytes, sum(len(members[name]) for name in source_names))
        self.assertEqual(digest, hashlib.sha256(archive_bytes).hexdigest())

    def test_included_source_change_changes_manifest_and_bundle_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_project(root)
            first_archive, first_digest, _, _ = bundle_builder.build_bundle(root)
            (root / "src/app_contracts/signed_verifier_service.py").write_bytes(
                b"from .nested.profile import PROFILE\nSERVICE = PROFILE + '! '\n"
            )
            second_archive, second_digest, _, _ = bundle_builder.build_bundle(root)

        self.assertNotEqual(first_digest, second_digest)
        first_manifest = self._archive_members(first_archive)["MANIFEST.json"]
        second_manifest = self._archive_members(second_archive)["MANIFEST.json"]
        self.assertNotEqual(first_manifest, second_manifest)

    def test_launcher_import_is_included_in_transitive_source_closure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_project(root)
            (root / "scripts/serve_ephemeral_signed_verifier_https.py").write_bytes(
                b"from app_contracts.service import SERVICE\n"
            )
            archive_bytes, _, _, _ = bundle_builder.build_bundle(root)

        members = self._archive_members(archive_bytes)
        self.assertEqual(members["src/app_contracts/service.py"], b"SERVICE = 1\n")

    def test_symlink_is_rejected_before_any_archive_bytes_are_written(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_project(root)
            target = root / "src/app_contracts/signed_verifier_service.py"
            replacement = root / "src/app_contracts/replacement.py"
            target.unlink()
            replacement.write_text("SERVICE = 1\n", encoding="utf-8")
            target.symlink_to(replacement)
            output, errors = io.BytesIO(), io.StringIO()

            result = bundle_builder.main([], stdout=output, stderr=errors, project_root=root)

        self.assertEqual(result, 2)
        self.assertEqual(output.getvalue(), b"")
        self.assertEqual(errors.getvalue(), "verifier host bundle: build failed\n")

    def test_size_limit_is_rejected_before_any_archive_bytes_are_written(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_project(root)
            output, errors = io.BytesIO(), io.StringIO()
            with patch.object(bundle_builder, "_MAX_MEMBER_BYTES", 4):
                result = bundle_builder.main(
                    [], stdout=output, stderr=errors, project_root=root
                )

        self.assertEqual(result, 2)
        self.assertEqual(output.getvalue(), b"")
        self.assertEqual(errors.getvalue(), "verifier host bundle: build failed\n")

    def test_symlinked_parent_is_rejected_before_any_archive_bytes_are_written(self):
        with tempfile.TemporaryDirectory() as temporary:
            outer = Path(temporary)
            root = outer / "project"
            outside = outer / "outside"
            self._make_project(root)
            outside.mkdir()
            (outside / "app_contracts").mkdir()
            (outside / "app_contracts/service.py").write_text(
                "SERVICE = 1\n", encoding="utf-8"
            )
            (root / "src").rename(root / "src-original")
            (root / "src").symlink_to(outside, target_is_directory=True)
            output, errors = io.BytesIO(), io.StringIO()

            result = bundle_builder.main(
                [], stdout=output, stderr=errors, project_root=root
            )

        self.assertEqual(result, 2)
        self.assertEqual(output.getvalue(), b"")
        self.assertEqual(errors.getvalue(), "verifier host bundle: build failed\n")

    def test_cli_emits_only_archive_on_stdout_and_bounded_metadata_on_stderr(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_project(root)
            output, errors = io.BytesIO(), io.StringIO()
            result = bundle_builder.main(
                [], stdout=output, stderr=errors, project_root=root
            )

        self.assertEqual(result, 0)
        archive_bytes = output.getvalue()
        metadata = json.loads(errors.getvalue())
        self.assertEqual(metadata["schema"], "agent00x-verifier-host-bundle-report/v1")
        self.assertEqual(
            metadata["bundle_sha256"],
            "sha256:" + hashlib.sha256(archive_bytes).hexdigest(),
        )
        self.assertEqual(metadata["member_count"], 9)
        self.assertEqual(
            set(metadata), {"schema", "bundle_sha256", "member_count", "source_bytes"}
        )

    def test_cli_rejects_arguments_before_emitting_archive(self):
        output, errors = io.BytesIO(), io.StringIO()

        result = bundle_builder.main(
            ["--help"], stdout=output, stderr=errors, project_root=ROOT
        )

        self.assertEqual(result, 2)
        self.assertEqual(output.getvalue(), b"")
        self.assertEqual(errors.getvalue(), "verifier host bundle: build failed\n")

    def test_cli_expected_digest_emits_archive_only_when_it_matches(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_project(root)
            expected_archive, digest, _, _ = bundle_builder.build_bundle(root)
            output, errors = io.BytesIO(), io.StringIO()
            result = bundle_builder.main(
                ["--expected-sha256", "sha256:" + digest],
                stdout=output,
                stderr=errors,
                project_root=root,
            )

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue(), expected_archive)
        report = json.loads(errors.getvalue())
        self.assertEqual(report["bundle_sha256"], "sha256:" + digest)

    def test_cli_digest_mismatch_and_malformed_arguments_emit_no_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._make_project(root)
            cases = [
                ["--expected-sha256", "sha256:" + "0" * 64],
                ["--expected-sha256", "not-a-digest"],
                ["--expected-sha256", "sha256:" + "a" * 64, "extra"],
            ]
            for arguments in cases:
                with self.subTest(arguments=arguments):
                    output, errors = io.BytesIO(), io.StringIO()
                    result = bundle_builder.main(
                        arguments,
                        stdout=output,
                        stderr=errors,
                        project_root=root,
                    )
                    self.assertEqual(result, 2)
                    self.assertEqual(output.getvalue(), b"")
                    self.assertEqual(
                        errors.getvalue(), "verifier host bundle: build failed\n"
                    )

    def test_process_cli_does_not_ignore_unexpected_arguments(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/build_verifier_host_bundle.py"), "--help"],
            env={"PYTHONDONTWRITEBYTECODE": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"verifier host bundle: build failed\n")

    def test_real_manifest_pins_exact_runtime_dependency_set(self):
        manifest_path = ROOT / "requirements-verifier-host.txt"
        raw = manifest_path.read_bytes()
        text = raw.decode("ascii")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        pins = []
        for line in lines:
            name, separator, version = line.partition("==")
            self.assertEqual(separator, "==")
            self.assertTrue(name)
            self.assertTrue(version)
            pins.append(f"{name.lower()}=={version}")
        self.assertEqual(len(pins), len(set(pins)))
        self.assertEqual(set(pins), set(_EXPECTED_VERIFIER_HOST_PINS))

        archive_bytes, _, _, _ = bundle_builder.build_bundle(ROOT)
        members = self._archive_members(archive_bytes)
        self.assertEqual(
            members["requirements-verifier-host.txt"],
            raw,
        )

    def test_real_verifier_bundle_includes_protocol_but_not_secret_readers(self):
        archive_bytes, _, _, _ = bundle_builder.build_bundle(ROOT)
        members = self._archive_members(archive_bytes)

        self.assertIn("src/app_contracts/credential_protocol.py", members)
        self.assertNotIn("src/app_contracts/credential_source.py", members)

    def test_real_bundle_imports_launcher_after_extraction_without_starting_service(self):
        archive_bytes, digest, count, source_bytes = bundle_builder.build_bundle(ROOT)
        self.assertEqual(digest, transfer.BUNDLE_SHA256)
        self.assertEqual(len(archive_bytes), transfer.BUNDLE_ARCHIVE_BYTES)
        self.assertEqual(count, transfer.BUNDLE_MEMBER_COUNT)
        self.assertEqual(source_bytes, transfer.BUNDLE_SOURCE_BYTES)
        with tempfile.TemporaryDirectory() as temporary:
            extracted = Path(temporary)
            with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
                members = archive.getmembers()
                self.assertEqual(len(members), count + 1)
                for member in members:
                    path = PurePosixPath(member.name)
                    self.assertTrue(member.isfile())
                    self.assertFalse(path.is_absolute())
                    self.assertNotIn("..", path.parts)
                    target = extracted.joinpath(*path.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.extractfile(member).read())
            launcher = extracted / "scripts/serve_ephemeral_signed_verifier_https.py"
            result = subprocess.run(
                [sys.executable, "-B", str(launcher), "--help"],
                cwd=extracted,
                env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertIn(b"--port PORT", result.stdout)
        self.assertEqual(result.stderr, b"")


if __name__ == "__main__":
    unittest.main()
