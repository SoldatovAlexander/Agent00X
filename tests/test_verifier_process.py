from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.executor import (
    ExecutionError,
    VerifierInput,
    VerifierResult,
    VerifierVerdict,
)
from app_contracts.verifier_process import (
    VERIFIER_PROCESS_SCHEMA_VERSION,
    VerifierProcessError,
    VerifierProcessRequest,
    VerifierProcessResponse,
    bind_verifier_response,
    digest_verifier_request,
    parse_verifier_request,
    parse_verifier_response,
    serialize_verifier_request,
)


def valid_verifier_input() -> VerifierInput:
    return VerifierInput(
        process_id="process-local-001",
        repository_id="fixture-repository",
        base_commit="a" * 40,
        snapshot_tree_digest="sha256:" + "1" * 64,
        declared_change_paths=("calculator.py",),
        verified_contents=(("calculator.py", "verified source contents"),),
        test_command=("python3", "-m", "unittest"),
        test_timeout_seconds=30,
        patch_digest="sha256:" + "2" * 64,
        evidence_digest="sha256:" + "3" * 64,
        verification_digest="sha256:" + "4" * 64,
        verified_contents_digest="sha256:" + "5" * 64,
        replay_result_digest="sha256:" + "6" * 64,
    )


def valid_verifier_result() -> VerifierResult:
    prepared = valid_verifier_input()
    return VerifierResult(
        process_id=prepared.process_id,
        base_commit=prepared.base_commit,
        snapshot_tree_digest=prepared.snapshot_tree_digest,
        replay_result_digest=prepared.replay_result_digest,
        verifier_id="local-fixture-verifier",
        patch_digest=prepared.patch_digest,
        evidence_digest=prepared.evidence_digest,
        verification_digest=prepared.verification_digest,
        verified_contents_digest=prepared.verified_contents_digest,
        verdict=VerifierVerdict.PASS,
    )


class VerifierProcessRecordTests(unittest.TestCase):
    def test_request_record_is_versioned_and_has_only_verifier_input_fields(self):
        request = VerifierProcessRequest.from_verifier_input(valid_verifier_input())

        self.assertEqual(request.schema_version, VERIFIER_PROCESS_SCHEMA_VERSION)
        payload = asdict(request)
        self.assertEqual(set(payload), {"schema_version", "verifier_input"})
        self.assertEqual(
            set(payload["verifier_input"]),
            {
                "process_id", "repository_id", "base_commit", "snapshot_tree_digest",
                "declared_change_paths", "verified_contents", "test_command",
                "test_timeout_seconds", "patch_digest", "evidence_digest",
                "verification_digest", "verified_contents_digest", "evidence_origin",
                "replay_result_digest",
            },
        )
        serialized = repr(payload)
        for forbidden_field in (
            "snapshot_path", "workspace", "environment", "stdout", "stderr",
            "credential", "capability",
        ):
            self.assertNotIn(forbidden_field, serialized)

    def test_response_record_contains_only_bounded_verifier_result_fields(self):
        response = VerifierProcessResponse.from_verifier_result(valid_verifier_result())

        self.assertEqual(response.schema_version, VERIFIER_PROCESS_SCHEMA_VERSION)
        payload = asdict(response)
        self.assertEqual(set(payload), {"schema_version", "verifier_result"})
        self.assertEqual(
            set(payload["verifier_result"]),
            {
                "process_id", "base_commit", "snapshot_tree_digest", "replay_result_digest",
                "verifier_id", "patch_digest", "evidence_digest", "verification_digest",
                "verified_contents_digest", "verdict", "blocker_codes", "evidence_origin",
            },
        )
        self.assertNotIn("verified source contents", repr(payload))

    def test_records_are_immutable_and_reject_invalid_types_or_versions(self):
        request = VerifierProcessRequest.from_verifier_input(valid_verifier_input())
        response = VerifierProcessResponse.from_verifier_result(valid_verifier_result())

        with self.assertRaises(FrozenInstanceError):
            request.schema_version = 2  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            response.verifier_result = valid_verifier_result()  # type: ignore[misc]
        for bad_version in (True, 0, "1"):
            with self.subTest(record="request", version=bad_version):
                with self.assertRaisesRegex(
                    VerifierProcessError, "^verifier process: request version is invalid$"
                ):
                    VerifierProcessRequest(bad_version, valid_verifier_input())
            with self.subTest(record="response", version=bad_version):
                with self.assertRaisesRegex(
                    VerifierProcessError, "^verifier process: response version is invalid$"
                ):
                    VerifierProcessResponse(bad_version, valid_verifier_result())

        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: request shape is invalid$"
        ):
            VerifierProcessRequest.from_verifier_input({"verified_contents": "forged"})
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: response shape is invalid$"
        ):
            VerifierProcessResponse.from_verifier_result({"verdict": "pass"})

    def test_request_record_rejects_non_local_evidence_origin(self):
        malformed_input = VerifierInput(
            **{**valid_verifier_input().__dict__, "evidence_origin": "remote-test"}
        )
        with self.assertRaisesRegex(
            VerifierProcessError,
            "^verifier process: request fields are invalid$",
        ):
            VerifierProcessRequest.from_verifier_input(malformed_input)

    def test_request_serialization_is_canonical_utf8_and_does_not_mutate_input(self):
        request = VerifierProcessRequest.from_verifier_input(
            VerifierInput(
                **{
                    **valid_verifier_input().__dict__,
                    "verified_contents": (("calculator.py", "café"),),
                }
            )
        )
        original = request.verifier_input

        first = serialize_verifier_request(request)
        second = serialize_verifier_request(
            VerifierProcessRequest.from_verifier_input(
                VerifierInput(**request.verifier_input.__dict__)
            )
        )

        self.assertIsInstance(first, bytes)
        self.assertEqual(first, second)
        self.assertIn("café".encode("utf-8"), first)
        self.assertNotIn(b"\\u00e9", first)
        self.assertFalse(first.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(request.verifier_input, original)
        self.assertFalse(first.endswith(b"\n"))

    def test_request_serialization_rejects_non_json_values_without_echo(self):
        malformed_input = VerifierInput(
            **{
                **valid_verifier_input().__dict__,
                "test_command": ("python3", object()),
            }
        )
        with self.assertRaisesRegex(
            VerifierProcessError,
            "^verifier process: request serialization failed$",
        ) as raised:
            serialize_verifier_request(
                VerifierProcessRequest.from_verifier_input(malformed_input)
            )
        self.assertNotIn("object at", str(raised.exception))


class VerifierRequestParsingTests(unittest.TestCase):
    def test_canonical_bytes_round_trip_to_equal_record(self):
        request = VerifierProcessRequest.from_verifier_input(valid_verifier_input())
        parsed = parse_verifier_request(serialize_verifier_request(request))
        self.assertEqual(parsed, request)
        self.assertEqual(
            serialize_verifier_request(parsed), serialize_verifier_request(request)
        )

    def test_non_bytes_or_bad_encoding_is_rejected(self):
        request = serialize_verifier_request(
            VerifierProcessRequest.from_verifier_input(valid_verifier_input())
        )
        for data in (None, "not-bytes", 42, bytearray(request), b"\xff\xfe{\x22}"):
            with self.subTest(data=repr(data)[:40]):
                with self.assertRaisesRegex(
                    VerifierProcessError,
                    "^verifier process: request encoding is invalid$",
                ):
                    parse_verifier_request(data)

    def test_malformed_json_shape_is_rejected(self):
        for data in (
            b"", b"[]", b'"request"', b"123", b"null", b"NaN", b"Infinity",
            b'{"schema_version": 1, "verifier_input": {},} trailing',
        ):
            with self.subTest(data=data[:40]):
                with self.assertRaisesRegex(
                    VerifierProcessError,
                    "^verifier process: request payload is invalid$",
                ):
                    parse_verifier_request(data)
        with self.subTest(data="missing-verifier-input"):
            with self.assertRaisesRegex(
                VerifierProcessError,
                "^verifier process: request fields are invalid$",
            ):
                parse_verifier_request(b'{"schema_version": 1}')
        nan_payload = (
            b'{"schema_version": 1, "verifier_input": '
            b'{"test_timeout_seconds": NaN}}'
        )
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: request payload is invalid$"
        ):
            parse_verifier_request(nan_payload)

    def test_only_stated_version_and_exact_field_set_parse(self):
        encoded = serialize_verifier_request(
            VerifierProcessRequest.from_verifier_input(valid_verifier_input())
        )
        for version in (b"0", b"2", b'"1"', b"true"):
            tampered = b'{"schema_version": ' + version + b', "verifier_input": {}}'
            with self.subTest(version=version):
                with self.assertRaisesRegex(
                    VerifierProcessError,
                    "^verifier process: request version is invalid$",
                ):
                    parse_verifier_request(tampered)
        import json as json_module

        payload = json_module.loads(encoded.decode("utf-8"))
        for mutate in (
            lambda mapping: {key: value for key, value in mapping.items()
                             if key != "verifier_input"},
            lambda mapping: {**mapping, "extra": 1},
            lambda mapping: {**mapping, "verifier_input": {
                key: value for key, value in mapping["verifier_input"].items()
                if key != "process_id"}},
            lambda mapping: {**mapping, "verifier_input": {
                **mapping["verifier_input"], "unknown": "x"}},
        ):
            tampered = json_module.dumps(mutate(payload)).encode("utf-8")
            with self.assertRaisesRegex(
                VerifierProcessError,
                "^verifier process: request fields are invalid$",
            ):
                parse_verifier_request(tampered)

    def test_non_local_evidence_origin_is_rejected(self):
        import json as json_module

        encoded = serialize_verifier_request(
            VerifierProcessRequest.from_verifier_input(valid_verifier_input())
        )
        payload = json_module.loads(encoded.decode("utf-8"))
        payload["verifier_input"]["evidence_origin"] = "remote-test"
        tampered = json_module.dumps(payload).encode("utf-8")
        with self.assertRaisesRegex(
            VerifierProcessError,
            "^verifier process: request fields are invalid$",
        ):
            parse_verifier_request(tampered)

    def test_duplicate_keys_are_rejected_at_every_level(self):
        top_duplicate = (
            b'{"schema_version": 1, "schema_version": 1, "verifier_input": {}}'
        )
        nested_duplicate = (
            b'{"schema_version": 1, "verifier_input": '
            b'{"process_id": "a", "process_id": "b"}}'
        )
        for data in (top_duplicate, nested_duplicate):
            with self.subTest(data=data[:60]):
                with self.assertRaisesRegex(
                    VerifierProcessError,
                    "^verifier process: request payload is invalid$",
                ):
                    parse_verifier_request(data)

    def test_bad_scalar_types_are_rejected(self):
        import json as json_module

        encoded = serialize_verifier_request(
            VerifierProcessRequest.from_verifier_input(valid_verifier_input())
        )
        payload = json_module.loads(encoded.decode("utf-8"))
        bad_values = {
            "process_id": (42, None),
            "patch_digest": (7,),
            "evidence_origin": (None,),
            "snapshot_tree_digest": (42,),
            "replay_result_digest": (False,),
            "test_timeout_seconds": ("30", True, 30.5),
            "declared_change_paths": ("calculator.py", [42], None),
            "test_command": (["python3", None],),
            "verified_contents": (
                "contents", [["only-path"]], [[1, 2]], [["a", "b", "c"]],
                {"calculator.py": "x"},
            ),
        }
        for field, values in bad_values.items():
            for value in values:
                with self.subTest(field=field, value=repr(value)[:30]):
                    tampered_input = dict(payload["verifier_input"], **{field: value})
                    tampered = json_module.dumps(
                        {"schema_version": 1, "verifier_input": tampered_input}
                    ).encode("utf-8")
                    with self.assertRaisesRegex(
                        VerifierProcessError,
                        "^verifier process: request fields are invalid$",
                    ):
                        parse_verifier_request(tampered)

    def test_parsing_errors_never_echo_raw_values(self):
        canary = "PARSE-CANARY-SECRET-VALUE"
        malformed = (
            b'{"schema_version": 1, "unknown": "' + canary.encode() + b'"}',
            b'{"schema_version": 1, "verifier_input": {"process_id": "' + canary.encode() + b'"}}',
            b'{"schema_version": 2, "note": "' + canary.encode() + b'"}',
            canary.encode(),
        )
        for data in malformed:
            with self.subTest(data=data[:40]):
                with self.assertRaises(VerifierProcessError) as raised:
                    parse_verifier_request(data)
                self.assertNotIn(canary, str(raised.exception))


class VerifierRequestDigestTests(unittest.TestCase):
    EXPECTED_FIXTURE_DIGEST = (
        "sha256:612127173a24c53bcb2cb55ce2153db552e62a18ad4cdca36451b43dde396cb6"
    )

    def test_digest_is_canonical_and_pinned(self):
        request = VerifierProcessRequest.from_verifier_input(valid_verifier_input())
        digest = digest_verifier_request(request)
        self.assertEqual(digest, self.EXPECTED_FIXTURE_DIGEST)
        self.assertRegex(digest, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(digest_verifier_request(request), digest)

    def test_any_bound_field_change_mismatches_digest(self):
        baseline = digest_verifier_request(
            VerifierProcessRequest.from_verifier_input(valid_verifier_input())
        )
        alternates = {
            "process_id": "process-forged-001",
            "repository_id": "repository-forged",
            "base_commit": "b" * 40,
            "snapshot_tree_digest": "sha256:" + "f" * 64,
            "declared_change_paths": ("other.py",),
            "verified_contents": (("other.py", "other contents"),),
            "test_command": ("python3", "-m", "pytest"),
            "test_timeout_seconds": 31,
            "patch_digest": "sha256:" + "e" * 64,
            "evidence_digest": "sha256:" + "d" * 64,
            "verification_digest": "sha256:" + "c" * 64,
            "verified_contents_digest": "sha256:" + "b" * 64,
            "replay_result_digest": None,
        }
        for field, value in alternates.items():
            with self.subTest(field=field):
                forged = VerifierProcessRequest.from_verifier_input(
                    VerifierInput(**{**valid_verifier_input().__dict__, field: value})
                )
                self.assertNotEqual(digest_verifier_request(forged), baseline)

    def test_digest_rejects_non_request_without_echo(self):
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: request shape is invalid$"
        ) as raised:
            digest_verifier_request({"verifier_input": "forged"})
        self.assertNotIn("forged", str(raised.exception))

    def test_digest_is_documented_as_change_detection_only(self):
        import app_contracts.verifier_process as module

        documented = (module.__doc__ or "") + (
            module.digest_verifier_request.__doc__ or ""
        )
        self.assertNotIn("signature", documented.lower())
        self.assertNotIn("proof", documented.lower())


class VerifierRequestBoundsTests(unittest.TestCase):
    def test_file_count_limit(self):
        oversized = VerifierProcessRequest.from_verifier_input(
            VerifierInput(
                **{
                    **valid_verifier_input().__dict__,
                    "verified_contents": tuple(
                        (f"file-{index}.py", "x") for index in range(21)
                    ),
                }
            )
        )
        with self.assertRaisesRegex(
            VerifierProcessError,
            "^verifier process: request file count exceeds limit$",
        ):
            serialize_verifier_request(oversized)
        boundary = VerifierProcessRequest.from_verifier_input(
            VerifierInput(
                **{
                    **valid_verifier_input().__dict__,
                    "verified_contents": tuple(
                        (f"file-{index}.py", "x") for index in range(20)
                    ),
                }
            )
        )
        self.assertTrue(serialize_verifier_request(boundary))

    def test_path_content_and_total_limits(self):
        base = valid_verifier_input().__dict__
        cases = [
            (
                {"verified_contents": (("p" * 238 + ".py", "x"),)},
                "^verifier process: request path exceeds limit$",
            ),
            (
                {"verified_contents": (("calculator.py", "x" * 100_001),)},
                "^verifier process: request content exceeds limit$",
            ),
            (
                {
                    "verified_contents": tuple(
                        (f"file-{index}.py", "x" * 100_000) for index in range(11)
                    )
                },
                "^verifier process: request contents exceed limit$",
            ),
        ]
        for override, message in cases:
            with self.subTest(message=message):
                oversized = VerifierProcessRequest.from_verifier_input(
                    VerifierInput(**{**base, **override})
                )
                with self.assertRaisesRegex(VerifierProcessError, message):
                    serialize_verifier_request(oversized)

    def test_total_wire_size_limit(self):
        oversized = VerifierProcessRequest.from_verifier_input(
            VerifierInput(
                **{
                    **valid_verifier_input().__dict__,
                    "process_id": "x" * 3_000_000,
                }
            )
        )
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: request size exceeds limit$"
        ):
            serialize_verifier_request(oversized)
        valid = VerifierProcessRequest.from_verifier_input(valid_verifier_input())
        self.assertLess(len(serialize_verifier_request(valid)), 100_000)

    def test_limit_errors_never_reveal_oversized_contents(self):
        canary = "BOUNDS-CANARY-SECRET-CONTENTS"
        oversized_values = (
            {"verified_contents": (("calculator.py", canary * 20_000),)},
            {"process_id": canary * 200_000},
        )
        for override in oversized_values:
            with self.subTest(override=tuple(override)):
                oversized = VerifierProcessRequest.from_verifier_input(
                    VerifierInput(**{**valid_verifier_input().__dict__, **override})
                )
                with self.assertRaises(VerifierProcessError) as raised:
                    serialize_verifier_request(oversized)
                self.assertNotIn(canary, str(raised.exception))


def valid_response_payload(**overrides):
    payload = {
        "process_id": "process-local-001",
        "base_commit": "a" * 40,
        "snapshot_tree_digest": "sha256:" + "1" * 64,
        "replay_result_digest": "sha256:" + "6" * 64,
        "verifier_id": "local-fixture-verifier",
        "patch_digest": "sha256:" + "2" * 64,
        "evidence_digest": "sha256:" + "3" * 64,
        "verification_digest": "sha256:" + "4" * 64,
        "verified_contents_digest": "sha256:" + "5" * 64,
        "verdict": "pass",
        "blocker_codes": [],
        "evidence_origin": "local_test",
    }
    payload.update(overrides)
    return payload


def encode_response_payload(result_payload):
    import json as json_module

    return json_module.dumps(
        {"schema_version": 1, "verifier_result": result_payload},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class VerifierResponseParsingTests(unittest.TestCase):
    def test_valid_child_output_restores_typed_bounded_result(self):
        response = parse_verifier_response(
            encode_response_payload(valid_response_payload())
        )
        expected = VerifierProcessResponse.from_verifier_result(valid_verifier_result())
        self.assertEqual(response, expected)
        self.assertIs(response.verifier_result.verdict, VerifierVerdict.PASS)
        self.assertEqual(response.verifier_result.blocker_codes, ())
        for verdict, member in (
            ("pass", VerifierVerdict.PASS),
            ("fail", VerifierVerdict.FAIL),
            ("blocked", VerifierVerdict.BLOCKED),
        ):
            with self.subTest(verdict=verdict):
                parsed = parse_verifier_response(
                    encode_response_payload(valid_response_payload(verdict=verdict))
                )
                self.assertIs(parsed.verifier_result.verdict, member)

    def test_version_and_field_set_are_strict(self):
        for version in (b"0", b"2", b'"1"', b"true"):
            data = b'{"schema_version": ' + version + b', "verifier_result": {}}'
            with self.subTest(version=version):
                with self.assertRaisesRegex(
                    VerifierProcessError,
                    "^verifier process: response version is invalid$",
                ):
                    parse_verifier_response(data)
        for mutate in (
            lambda payload: {"schema_version": 1},
            lambda payload: {"schema_version": 1, "verifier_result": payload,
                             "extra": True},
            lambda payload: {"schema_version": 1, "verifier_result": {
                key: value for key, value in payload.items() if key != "verdict"}},
            lambda payload: {"schema_version": 1, "verifier_result": {
                **payload, "unknown": []}},
        ):
            with self.assertRaisesRegex(
                VerifierProcessError,
                "^verifier process: response fields are invalid$",
            ):
                parse_verifier_response(
                    encode_response_payload(mutate(valid_response_payload()))
                    if not isinstance(mutate(valid_response_payload()), bytes)
                    else mutate(valid_response_payload())
                )

    def test_malformed_encoding_shape_and_duplicates_fail_closed(self):
        for data in (None, 42, b"\xff\xfe{}", b"", b"[]", b"NaN"):
            with self.subTest(data=repr(data)[:30]):
                with self.assertRaises(VerifierProcessError):
                    parse_verifier_response(data)
        duplicates = (
            b'{"schema_version": 1, "schema_version": 1, "verifier_result": {}}',
            b'{"schema_version": 1, "verifier_result": '
            b'{"verdict": "pass", "verdict": "fail"}}',
        )
        for data in duplicates:
            with self.subTest(data=data[:50]):
                with self.assertRaisesRegex(
                    VerifierProcessError,
                    "^verifier process: response payload is invalid$",
                ):
                    parse_verifier_response(data)

    def test_malformed_values_fail_closed_without_echo(self):
        canary = "RESPONSE-CANARY-SECRET-VALUE"
        malformed = {
            "process_id": (42, None),
            "verifier_id": (["nested"],),
            "snapshot_tree_digest": (17,),
            "replay_result_digest": (False,),
            "evidence_origin": (None,),
            "verdict": ("unknown", "PASS", "", None, 42, True),
            "blocker_codes": (
                "not-a-list",
                ["ok", 42],
                ["BAD-UPPER"],
                [""],
                ["a" * 65],
                ["has space"],
                ["-leading"],
                [canary],
                tuple(f"blocker-{index}" for index in range(17)),
            ),
        }
        for field, values in malformed.items():
            for value in values:
                with self.subTest(field=field, value=repr(value)[:30]):
                    with self.assertRaisesRegex(
                        VerifierProcessError,
                        "^verifier process: response fields are invalid$",
                    ) as raised:
                        parse_verifier_response(
                            encode_response_payload(valid_response_payload(**{field: value}))
                        )
                    self.assertNotIn(canary, str(raised.exception))
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: response fields are invalid$"
        ) as raised:
            parse_verifier_response(
                b'{"schema_version": 1, "verifier_result": {"verdict": "' + canary.encode() + b'"}}'
            )
        self.assertNotIn(canary, str(raised.exception))


def valid_bound_trio():
    request = VerifierProcessRequest.from_verifier_input(valid_verifier_input())
    digest = digest_verifier_request(request)
    response = parse_verifier_response(
        encode_response_payload(valid_response_payload())
    )
    return request, digest, response


class VerifierResponseBindingTests(unittest.TestCase):
    def test_matching_trio_returns_typed_result(self):
        request, digest, response = valid_bound_trio()
        result = bind_verifier_response(request, digest, response)
        self.assertEqual(result, response.verifier_result)
        self.assertIsInstance(result, VerifierResult)
        self.assertIs(result.verdict, VerifierVerdict.PASS)

    def test_request_digest_must_match_exact_source_request(self):
        request, digest, response = valid_bound_trio()
        for forged_digest in (None, 42, "", "sha256:" + "f" * 64, digest + "tampered"):
            with self.subTest(digest=repr(forged_digest)[:30]):
                with self.assertRaisesRegex(
                    VerifierProcessError,
                    "^verifier process: request digest mismatch$",
                ):
                    bind_verifier_response(request, forged_digest, response)
        tampered_request = VerifierProcessRequest.from_verifier_input(
            VerifierInput(
                **{**valid_verifier_input().__dict__, "process_id": "process-forged-001"}
            )
        )
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: request digest mismatch$"
        ):
            bind_verifier_response(tampered_request, digest, response)

    def test_any_binding_substitution_uses_existing_executor_contract(self):
        request, digest, response = valid_bound_trio()
        for field, value in (
            ("process_id", "process-foreign-001"),
            ("base_commit", "b" * 40),
            ("snapshot_tree_digest", "sha256:" + "f" * 64),
            ("replay_result_digest", "sha256:" + "e" * 64),
            ("patch_digest", "sha256:" + "d" * 64),
            ("evidence_digest", "sha256:" + "c" * 64),
            ("verification_digest", "sha256:" + "b" * 64),
            ("verified_contents_digest", "sha256:" + "a" * 64),
        ):
            with self.subTest(field=field):
                forged_result = VerifierResult(
                    **{**response.verifier_result.__dict__, field: value}
                )
                forged_response = VerifierProcessResponse(
                    VERIFIER_PROCESS_SCHEMA_VERSION, forged_result
                )
                with self.assertRaisesRegex(
                    ExecutionError, "^execution verifier: result binding mismatch$"
                ):
                    bind_verifier_response(request, digest, forged_response)

    def test_malformed_binding_inputs_fail_closed_without_echo(self):
        canary = "BIND-CANARY-SECRET-VALUE"
        request, digest, response = valid_bound_trio()
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: request shape is invalid$"
        ):
            bind_verifier_response({"forged": canary}, digest, response)
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: response shape is invalid$"
        ):
            bind_verifier_response(request, digest, {"verdict": canary})
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: request digest mismatch$"
        ) as raised:
            bind_verifier_response(request, canary, response)
        self.assertNotIn(canary, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
