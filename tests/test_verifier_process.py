from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.executor import (
    ExecutionError,
    IndependentVerifier,
    VerifierInput,
    VerifierResult,
    VerifierVerdict,
)
from app_contracts.verifier_process import (
    MAX_VERIFIER_COMMAND_TIMEOUT_SECONDS,
    MAX_VERIFIER_RESPONSE_BYTES,
    VERIFIER_PROCESS_SCHEMA_VERSION,
    SubprocessVerifier,
    VerifierProcessConfig,
    VerifierProcessError,
    VerifierProcessOutcome,
    VerifierProcessRequest,
    VerifierProcessResponse,
    bind_verifier_response,
    classify_verifier_outcome,
    digest_verifier_request,
    parse_verifier_request,
    parse_verifier_response,
    run_verifier_command,
    serialize_verifier_request,
    verifier_child_environ,
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


VALID_REQUEST_DIGEST = (
    "sha256:612127173a24c53bcb2cb55ce2153db552e62a18ad4cdca36451b43dde396cb6"
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
        response = VerifierProcessResponse.from_verifier_result(
            valid_verifier_result(), VALID_REQUEST_DIGEST
        )

        self.assertEqual(response.schema_version, VERIFIER_PROCESS_SCHEMA_VERSION)
        payload = asdict(response)
        self.assertEqual(
            set(payload), {"schema_version", "request_digest", "verifier_result"}
        )
        self.assertEqual(payload["request_digest"], VALID_REQUEST_DIGEST)
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
        response = VerifierProcessResponse.from_verifier_result(
            valid_verifier_result(), VALID_REQUEST_DIGEST
        )

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
                    VerifierProcessResponse(
                        bad_version, VALID_REQUEST_DIGEST, valid_verifier_result()
                    )

        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: request shape is invalid$"
        ):
            VerifierProcessRequest.from_verifier_input({"verified_contents": "forged"})
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: response shape is invalid$"
        ):
            VerifierProcessResponse.from_verifier_result(
                {"verdict": "pass"}, VALID_REQUEST_DIGEST
            )
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: response fields are invalid$"
        ):
            VerifierProcessResponse.from_verifier_result(
                valid_verifier_result(), "not-a-digest"
            )

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
            "^verifier process: request fields are invalid$",
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
    EXPECTED_FIXTURE_DIGEST = VALID_REQUEST_DIGEST

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

    def test_wire_size_exact_boundary_is_accepted_and_next_byte_is_rejected(self):
        from app_contracts.verifier_process import MAX_VERIFIER_REQUEST_BYTES

        base_input = valid_verifier_input()
        base_request = VerifierProcessRequest.from_verifier_input(base_input)
        base_size = len(serialize_verifier_request(base_request))
        process_id = base_input.process_id

        def request_for_size(size: int) -> VerifierProcessRequest:
            target_length = len(process_id) + size - base_size
            return VerifierProcessRequest.from_verifier_input(
                VerifierInput(**{**base_input.__dict__, "process_id": "x" * target_length})
            )

        exact = serialize_verifier_request(request_for_size(MAX_VERIFIER_REQUEST_BYTES))
        self.assertEqual(len(exact), MAX_VERIFIER_REQUEST_BYTES)
        self.assertTrue(parse_verifier_request(exact))

        over = request_for_size(MAX_VERIFIER_REQUEST_BYTES + 1)
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: request size exceeds limit$"
        ):
            serialize_verifier_request(over)
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: request size exceeds limit$"
        ):
            parse_verifier_request(exact + b" ")

    def test_all_request_strings_and_collections_are_bounded_before_serialization(self):
        from app_contracts.verifier_process import MAX_VERIFIER_REQUEST_COMMAND_ARGS

        base = valid_verifier_input().__dict__
        oversized_inputs = (
            {"declared_change_paths": tuple(f"{index}.py" for index in range(21))},
            {"test_command": tuple("x" for _ in range(MAX_VERIFIER_REQUEST_COMMAND_ARGS + 1))},
            {"test_command": ("x" * 3_000_000,)},
            {"repository_id": "x" * 3_000_000},
        )
        for override in oversized_inputs:
            with self.subTest(field=next(iter(override))):
                request = VerifierProcessRequest.from_verifier_input(
                    VerifierInput(**{**base, **override})
                )
                with self.assertRaises(VerifierProcessError):
                    serialize_verifier_request(request)

    def test_parser_rejects_oversized_input_before_decoding(self):
        from app_contracts.verifier_process import MAX_VERIFIER_REQUEST_BYTES

        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: request size exceeds limit$"
        ):
            parse_verifier_request(b"\xff" * (MAX_VERIFIER_REQUEST_BYTES + 1))

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
        "request_digest": VALID_REQUEST_DIGEST,
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

    payload = dict(result_payload)
    request_digest = payload.pop("request_digest", VALID_REQUEST_DIGEST)
    return json_module.dumps(
        {
            "schema_version": 1,
            "request_digest": request_digest,
            "verifier_result": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class VerifierResponseParsingTests(unittest.TestCase):
    def test_valid_child_output_restores_typed_bounded_result(self):
        response = parse_verifier_response(
            encode_response_payload(valid_response_payload())
        )
        expected = VerifierProcessResponse.from_verifier_result(
            valid_verifier_result(), VALID_REQUEST_DIGEST
        )
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

    def test_request_digest_field_is_required_and_canonical(self):
        for value in (None, 42, "", "sha256:" + "A" * 64, "sha256:" + "f" * 63):
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(
                    VerifierProcessError,
                    "^verifier process: response fields are invalid$",
                ):
                    parse_verifier_response(
                        encode_response_payload(
                            valid_response_payload(request_digest=value)
                        )
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
        result = bind_verifier_response(request, response)
        self.assertEqual(result, response.verifier_result)
        self.assertIsInstance(result, VerifierResult)
        self.assertIs(result.verdict, VerifierVerdict.PASS)

    def test_response_digest_must_match_exact_source_request(self):
        request, digest, response = valid_bound_trio()
        forged_response = VerifierProcessResponse(
            VERIFIER_PROCESS_SCHEMA_VERSION,
            "sha256:" + "f" * 64,
            response.verifier_result,
        )
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: request digest mismatch$"
        ):
            bind_verifier_response(request, forged_response)
        tampered_request = VerifierProcessRequest.from_verifier_input(
            VerifierInput(
                **{**valid_verifier_input().__dict__, "process_id": "process-forged-001"}
            )
        )
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: request digest mismatch$"
        ):
            bind_verifier_response(tampered_request, response)

    def test_stale_response_for_different_test_command_is_rejected(self):
        request, digest, response = valid_bound_trio()
        foreign_request = VerifierProcessRequest.from_verifier_input(
            VerifierInput(
                **{
                    **valid_verifier_input().__dict__,
                    "test_command": ("python3", "-m", "pytest"),
                }
            )
        )
        self.assertNotEqual(digest_verifier_request(foreign_request), digest)
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: request digest mismatch$"
        ):
            bind_verifier_response(foreign_request, response)

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
                    VERIFIER_PROCESS_SCHEMA_VERSION, digest, forged_result
                )
                with self.assertRaisesRegex(
                    ExecutionError, "^execution verifier: result binding mismatch$"
                ):
                    bind_verifier_response(request, forged_response)

    def test_malformed_binding_inputs_fail_closed_without_echo(self):
        canary = "BIND-CANARY-SECRET-VALUE"
        request, digest, response = valid_bound_trio()
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: request shape is invalid$"
        ):
            bind_verifier_response({"forged": canary}, response)
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: response shape is invalid$"
        ):
            bind_verifier_response(request, {"verdict": canary})


def valid_process_config(**overrides):
    fields = {
        "executable": "/usr/local/bin/fixture-verifier",
        "argv": ("/usr/local/bin/fixture-verifier", "--verify"),
        "timeout_seconds": 30,
        "max_stdout_bytes": 1_000_000,
        "max_stderr_bytes": 100_000,
    }
    fields.update(overrides)
    return VerifierProcessConfig(**fields)


class VerifierProcessConfigTests(unittest.TestCase):
    def test_config_is_immutable_with_exact_bounded_shape(self):
        config = valid_process_config()
        self.assertEqual(
            set(VerifierProcessConfig.__dataclass_fields__),
            {
                "executable", "argv", "timeout_seconds",
                "max_stdout_bytes", "max_stderr_bytes",
            },
        )
        with self.assertRaises(FrozenInstanceError):
            config.timeout_seconds = 60  # type: ignore[misc]
        self.assertEqual(config.argv, ("/usr/local/bin/fixture-verifier", "--verify"))

    def test_config_accepts_boundary_values(self):
        boundary = valid_process_config(
            timeout_seconds=1, max_stdout_bytes=1, max_stderr_bytes=1
        )
        self.assertEqual(boundary.timeout_seconds, 1)
        ceiling = valid_process_config(
            timeout_seconds=MAX_VERIFIER_COMMAND_TIMEOUT_SECONDS,
            max_stdout_bytes=MAX_VERIFIER_RESPONSE_BYTES,
            max_stderr_bytes=MAX_VERIFIER_RESPONSE_BYTES,
        )
        self.assertEqual(ceiling.timeout_seconds, MAX_VERIFIER_COMMAND_TIMEOUT_SECONDS)

    def test_malformed_executable_is_rejected_without_echo(self):
        canary = "EXECUTABLE-CANARY-SECRET"
        for executable in (
            None, 42, "", "  ", "relative/verifier", "verifier",
            "/usr/local/bin/has space", f"/tmp/{canary}\n",
            "/trailing-slash/ ",
        ):
            with self.subTest(executable=repr(executable)[:40]):
                with self.assertRaisesRegex(
                    VerifierProcessError,
                    "^verifier process: command executable is invalid$",
                ) as raised:
                    valid_process_config(executable=executable)
                self.assertNotIn(canary, str(raised.exception))

    def test_malformed_argv_is_rejected_without_echo(self):
        canary = "ARGV-CANARY-SECRET"
        for argv in (
            None, "single-string", [], (), (None,), ("ok", 42), ("ok", ""),
            (canary, None),
        ):
            with self.subTest(argv=repr(argv)[:40]):
                with self.assertRaisesRegex(
                    VerifierProcessError,
                    "^verifier process: command arguments are invalid$",
                ) as raised:
                    valid_process_config(argv=argv)
                self.assertNotIn(canary, str(raised.exception))

    def test_malformed_timeout_and_limits_are_rejected(self):
        for timeout in (None, 0, -1, True, "30", 30.5, MAX_VERIFIER_COMMAND_TIMEOUT_SECONDS + 1):
            with self.subTest(timeout=repr(timeout)):
                with self.assertRaisesRegex(
                    VerifierProcessError,
                    "^verifier process: command timeout is invalid$",
                ):
                    valid_process_config(timeout_seconds=timeout)
        for field in ("max_stdout_bytes", "max_stderr_bytes"):
            for limit in (None, 0, -5, True, "1024", MAX_VERIFIER_RESPONSE_BYTES + 1):
                with self.subTest(field=field, limit=repr(limit)):
                    with self.assertRaisesRegex(
                        VerifierProcessError,
                        "^verifier process: response limits are invalid$",
                    ):
                        valid_process_config(**{field: limit})

    def test_process_layer_spawns_only_bounded_children(self):
        import ast

        source = Path(__file__).resolve().parents[1] / "src" / "app_contracts" / "verifier_process.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported = set()
        shell_true = False
        host_env_access = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").lower())
            elif isinstance(node, ast.keyword):
                if node.arg == "shell" and getattr(node.value, "value", None) is True:
                    shell_true = True
            elif isinstance(node, ast.Attribute):
                if node.attr == "environ":
                    host_env_access = True
        self.assertIn("subprocess", imported)
        self.assertTrue({"pty", "multiprocessing"}.isdisjoint(imported))
        self.assertFalse(shell_true)
        self.assertFalse(host_env_access)


class VerifierChildEnvironTests(unittest.TestCase):
    def test_default_environ_is_empty_and_explicit_mapping_is_copied(self):
        self.assertEqual(verifier_child_environ(), {})
        self.assertEqual(verifier_child_environ({}), {})
        provided = {"VERIFIER_MODE": "local-check"}
        built = verifier_child_environ(provided)
        self.assertEqual(built, provided)
        self.assertIsNot(built, provided)

    def test_malformed_extra_mapping_is_rejected_without_echo(self):
        canary = "ENV-CANARY-SECRET"
        for extra in (42, "VAR=1", [("A", "B")], {None: "v"}, {"": "v"}, {"A": 1},
                      {"A": None}, {canary: None}):
            with self.subTest(extra=repr(extra)[:40]):
                with self.assertRaisesRegex(
                    VerifierProcessError,
                    "^verifier process: child environment is invalid$",
                ) as raised:
                    verifier_child_environ(extra)
                self.assertNotIn(canary, str(raised.exception))

    def test_canary_parent_variable_is_absent_from_child(self):
        import json as json_module
        import os
        import subprocess

        canary_key = "APP_CONTRACTS_TEST_CANARY_VARIABLE"
        canary = "ENV-PARENT-CANARY-SECRET"
        os.environ[canary_key] = canary
        try:
            child = subprocess.run(
                [sys.executable, "-c",
                 "import json, os; print(json.dumps(dict(os.environ)))"],
                capture_output=True,
                text=True,
                timeout=60,
                env=verifier_child_environ({"VERIFIER_MODE": "local-check"}),
                check=False,
            )
        finally:
            del os.environ[canary_key]
        self.assertEqual(child.returncode, 0)
        child_environ = json_module.loads(child.stdout)
        self.assertEqual(child_environ.get("VERIFIER_MODE"), "local-check")
        self.assertNotIn(canary_key, child_environ)
        self.assertNotIn(canary, child.stdout)
        self.assertLessEqual(len(child_environ), 3)
        self.assertNotIn(canary_key, os.environ)


class VerifierCommandInvocationTests(unittest.TestCase):
    def test_child_receives_exact_canonical_request_bytes(self):
        import hashlib

        request = VerifierProcessRequest.from_verifier_input(valid_verifier_input())
        expected_hex = hashlib.sha256(serialize_verifier_request(request)).hexdigest()
        response_text = encode_response_payload(valid_response_payload()).decode("utf-8")
        script = (
            "import hashlib, json, sys; "
            "raw = sys.stdin.buffer.read(); "
            "payload = json.loads(raw.decode('utf-8')); "
            "forbidden = [key for key in ('snapshot_path', 'workspace', 'credential', "
            "'capability', 'environment') if key in repr(payload)]; "
            "clean = hashlib.sha256(raw).hexdigest() == sys.argv[1] and not forbidden; "
            "sys.stdout.write(sys.argv[2] if clean else 'tainted');"
        )
        config = valid_process_config(
            executable=sys.executable,
            argv=(sys.executable, "-c", script, expected_hex, response_text),
        )
        response = run_verifier_command(config, request)
        self.assertIsInstance(response, VerifierProcessResponse)
        self.assertEqual(
            response, parse_verifier_response(response_text.encode("utf-8"))
        )
        self.assertIs(response.verifier_result.verdict, VerifierVerdict.PASS)

    def test_timeout_kills_child_once_without_replay(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            counter = str(Path(directory) / "starts.txt")
            script = (
                "import sys, time; "
                "sys.stdin.buffer.read(); "
                f"open({counter!r}, 'a').write('started\\n'); "
                "time.sleep(30);"
            )
            config = valid_process_config(
                executable=sys.executable,
                argv=(sys.executable, "-c", script),
                timeout_seconds=1,
            )
            request = VerifierProcessRequest.from_verifier_input(valid_verifier_input())
            with self.assertRaisesRegex(
                VerifierProcessError, "^verifier process: child timed out$"
            ):
                run_verifier_command(config, request)
            self.assertEqual(Path(counter).read_text(encoding="utf-8"), "started\n")

    def test_malformed_inputs_fail_before_spawn(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            counter = str(Path(directory) / "starts.txt")
            script = f"open({counter!r}, 'a').write('started\\n');"
            config = valid_process_config(
                executable=sys.executable, argv=(sys.executable, "-c", script)
            )
            request = VerifierProcessRequest.from_verifier_input(valid_verifier_input())
            for bad_config, bad_request in (
                (None, request),
                ("not-a-config", request),
                (config, None),
                (config, "not-a-request"),
            ):
                with self.subTest(config=repr(bad_config)[:20]):
                    with self.assertRaises(VerifierProcessError):
                        run_verifier_command(bad_config, bad_request)
            self.assertFalse(Path(counter).exists())

    def test_launch_failure_is_stable_without_echo(self):
        canary = "LAUNCH-CANARY-SECRET-PATH"
        config = valid_process_config(executable=f"/nonexistent/{canary}")
        request = VerifierProcessRequest.from_verifier_input(valid_verifier_input())
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: child launch failed$"
        ) as raised:
            run_verifier_command(config, request)
        self.assertNotIn(canary, str(raised.exception))

    def test_outcome_record_rejects_malformed_values(self):
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: child outcome is invalid$"
        ):
            VerifierProcessOutcome(True, b"", b"")
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: child outcome is invalid$"
        ):
            VerifierProcessOutcome(0, "not-bytes", b"")


class VerifierOutputBoundsTests(unittest.TestCase):
    def test_over_limit_stdout_terminates_child_fail_closed(self):
        flood_bytes = 3_000_000
        script = (
            "import sys; "
            f"sys.stdout.buffer.write(b'Q' * {flood_bytes}); "
            "import time; time.sleep(30);"
        )
        config = valid_process_config(
            executable=sys.executable,
            argv=(sys.executable, "-c", script),
            timeout_seconds=30,
            max_stdout_bytes=100_000,
        )
        request = VerifierProcessRequest.from_verifier_input(valid_verifier_input())
        with self.assertRaisesRegex(
            VerifierProcessError,
            "^verifier process: child output exceeds limit$",
        ):
            run_verifier_command(config, request)
        follow_up_text = encode_response_payload(valid_response_payload()).decode("utf-8")
        follow_up = run_verifier_command(
            valid_process_config(
                executable=sys.executable,
                argv=(sys.executable, "-c", "import sys; sys.stdout.write(sys.argv[1]);",
                      follow_up_text),
            ),
            request,
        )
        self.assertIsInstance(follow_up, VerifierProcessResponse)

    def test_over_limit_stderr_never_reaches_errors(self):
        canary = "STDERR-CANARY-SECRET"
        script = (
            "import sys; "
            f"sys.stderr.buffer.write(({canary!r} * 40_000).encode()); "
        )
        config = valid_process_config(
            executable=sys.executable,
            argv=(sys.executable, "-c", script),
            max_stderr_bytes=100_000,
        )
        request = VerifierProcessRequest.from_verifier_input(valid_verifier_input())
        with self.assertRaisesRegex(
            VerifierProcessError,
            "^verifier process: child output exceeds limit$",
        ) as raised:
            run_verifier_command(config, request)
        self.assertNotIn(canary, str(raised.exception))

    def test_no_raw_streams_reach_caller(self):
        canary = "STREAM-CANARY-MARKER"
        record_text = encode_response_payload(valid_response_payload()).decode("utf-8")
        script = (
            "import sys; "
            "sys.stdout.write(sys.argv[1]); "
            f"sys.stderr.write({canary!r});"
        )
        config = valid_process_config(
            executable=sys.executable,
            argv=(sys.executable, "-c", script, record_text),
        )
        request = VerifierProcessRequest.from_verifier_input(valid_verifier_input())
        response = run_verifier_command(config, request)
        self.assertIsInstance(response, VerifierProcessResponse)
        self.assertEqual(response, parse_verifier_response(record_text.encode("utf-8")))
        self.assertFalse(hasattr(response, "stderr"))
        self.assertFalse(hasattr(response, "stdout"))
        self.assertNotIn(canary, repr(response))
        exact_cap = len(record_text.encode("utf-8"))
        boundary = run_verifier_command(
            valid_process_config(
                executable=sys.executable,
                argv=(sys.executable, "-c", "import sys; sys.stdout.write(sys.argv[1]);",
                      record_text),
                max_stdout_bytes=exact_cap,
            ),
            request,
        )
        self.assertIsInstance(boundary, VerifierProcessResponse)
        with self.assertRaisesRegex(
            VerifierProcessError,
            "^verifier process: child output exceeds limit$",
        ):
            run_verifier_command(
                valid_process_config(
                    executable=sys.executable,
                    argv=(sys.executable, "-c", "import sys; sys.stdout.write(sys.argv[1]);",
                          record_text),
                    max_stdout_bytes=exact_cap - 1,
                ),
                request,
            )

    def test_stdout_accepts_only_single_response_record(self):
        import json as json_module

        request = VerifierProcessRequest.from_verifier_input(valid_verifier_input())
        record = json_module.dumps(
            {"schema_version": 1, "verifier_result": "placeholder"},
            separators=(",", ":"),
        )
        script = f"import sys; sys.stdout.write({record!r} + {record!r});"
        config = valid_process_config(
            executable=sys.executable, argv=(sys.executable, "-c", script)
        )
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: child response is malformed$"
        ):
            run_verifier_command(config, request)


class VerifierOutcomeClassificationTests(unittest.TestCase):
    def test_nonzero_exit_becomes_stable_failure(self):
        canary = "EXIT-CANARY-SECRET"
        for exit_code in (1, 3):
            script = (
                "import sys; "
                f"sys.stderr.write({canary!r}); "
                f"sys.exit({exit_code});"
            )
            config = valid_process_config(
                executable=sys.executable, argv=(sys.executable, "-c", script)
            )
            request = VerifierProcessRequest.from_verifier_input(valid_verifier_input())
            with self.assertRaisesRegex(
                VerifierProcessError, "^verifier process: child exit failed$"
            ) as raised:
                run_verifier_command(config, request)
            self.assertNotIn(canary, str(raised.exception))

    def test_empty_response_becomes_stable_failure(self):
        outcome = VerifierProcessOutcome(0, b"", b"")
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: child response is empty$"
        ):
            classify_verifier_outcome(outcome)

    def test_malformed_response_becomes_stable_failure_without_echo(self):
        canary = "MALFORMED-CANARY-SECRET"
        for stdout in (
            canary.encode("utf-8"),
            b'{"schema_version": 1}',
            b'{"schema_version": 1, "verifier_result": {}, "extra": true}',
        ):
            with self.subTest(stdout=stdout[:30]):
                outcome = VerifierProcessOutcome(0, stdout, b"")
                with self.assertRaisesRegex(
                    VerifierProcessError,
                    "^verifier process: child response is malformed$",
                ) as raised:
                    classify_verifier_outcome(outcome)
                self.assertNotIn(canary, str(raised.exception))

    def test_well_formed_response_preserves_child_verdict(self):
        for verdict, member in (("pass", "PASS"), ("fail", "FAIL")):
            response = parse_verifier_response(
                encode_response_payload(valid_response_payload(verdict=verdict))
            )
            outcome = VerifierProcessOutcome(
                0, encode_response_payload(valid_response_payload(verdict=verdict)), b""
            )
            classified = classify_verifier_outcome(outcome)
            self.assertEqual(classified, response)
            self.assertIs(
                classified.verifier_result.verdict, getattr(VerifierVerdict, member)
            )

    def test_non_outcome_input_is_rejected(self):
        for value in (None, {}, (0, b"", b"")):
            with self.subTest(value=repr(value)[:20]):
                with self.assertRaisesRegex(
                    VerifierProcessError,
                    "^verifier process: child outcome is invalid$",
                ):
                    classify_verifier_outcome(value)

    def test_child_streams_never_reach_classified_results(self):
        canary = "STREAM-CANARY-SECRET"
        payload_text = encode_response_payload(valid_response_payload()).decode("utf-8")
        script = (
            "import sys; "
            f"sys.stderr.write({canary!r}); "
            "sys.stdout.write(sys.argv[1]);"
        )
        config = valid_process_config(
            executable=sys.executable,
            argv=(sys.executable, "-c", script, payload_text),
        )
        request = VerifierProcessRequest.from_verifier_input(valid_verifier_input())
        classified = run_verifier_command(config, request)
        self.assertNotIn(canary, repr(classified))


ECHOING_VERIFIER_SCRIPT = (
    "import hashlib, json, sys; "
    "raw = sys.stdin.buffer.read(); "
    "req = json.loads(raw.decode('utf-8'))['verifier_input']; "
    "result = {'process_id': req['process_id'], 'base_commit': req['base_commit'], "
    "'snapshot_tree_digest': req['snapshot_tree_digest'], "
    "'replay_result_digest': req['replay_result_digest'], "
    "'verifier_id': 'local-test-verifier', 'patch_digest': req['patch_digest'], "
    "'evidence_digest': req['evidence_digest'], "
    "'verification_digest': req['verification_digest'], "
    "'verified_contents_digest': req['verified_contents_digest'], "
    "'verdict': 'pass', 'blocker_codes': [], 'evidence_origin': 'local_test'}; "
    "sys.stdout.write(json.dumps({'schema_version': 1, "
    "'request_digest': 'sha256:' + hashlib.sha256(raw).hexdigest(), "
    "'verifier_result': result}, sort_keys=True, separators=(',', ':')));"
)


def expected_adapter_result() -> VerifierResult:
    prepared = valid_verifier_input()
    return VerifierResult(
        process_id=prepared.process_id,
        base_commit=prepared.base_commit,
        snapshot_tree_digest=prepared.snapshot_tree_digest,
        replay_result_digest=prepared.replay_result_digest,
        verifier_id="local-test-verifier",
        patch_digest=prepared.patch_digest,
        evidence_digest=prepared.evidence_digest,
        verification_digest=prepared.verification_digest,
        verified_contents_digest=prepared.verified_contents_digest,
        verdict=VerifierVerdict.PASS,
    )


class SubprocessVerifierAdapterTests(unittest.TestCase):
    def test_adapter_satisfies_verifier_protocol_with_typed_result(self):
        adapter = SubprocessVerifier(
            valid_process_config(
                executable=sys.executable,
                argv=(sys.executable, "-c", ECHOING_VERIFIER_SCRIPT),
            )
        )
        self.assertIsInstance(adapter, IndependentVerifier)
        result = adapter.verify(valid_verifier_input())
        self.assertIsInstance(result, VerifierResult)
        self.assertEqual(result, expected_adapter_result())
        self.assertIs(result.verdict, VerifierVerdict.PASS)

    def test_malformed_config_and_input_fail_before_spawn(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            counter = str(Path(directory) / "starts.txt")
            script = f"open({counter!r}, 'a').write('started\\n');"
            with self.assertRaisesRegex(
                VerifierProcessError, "^verifier process: command config is invalid$"
            ):
                SubprocessVerifier("not-a-config")
            adapter = SubprocessVerifier(
                valid_process_config(
                    executable=sys.executable, argv=(sys.executable, "-c", script)
                )
            )
            with self.assertRaisesRegex(
                VerifierProcessError, "^verifier process: request shape is invalid$"
            ):
                adapter.verify({"verifier_input": "forged"})
            self.assertFalse(Path(counter).exists())

    def test_failing_child_propagates_fail_closed_without_result(self):
        canary = "ADAPTER-FAILURE-CANARY"
        script = (
            "import sys; "
            f"sys.stderr.write({canary!r}); "
            "sys.exit(3);"
        )
        adapter = SubprocessVerifier(
            valid_process_config(
                executable=sys.executable, argv=(sys.executable, "-c", script)
            )
        )
        with self.assertRaisesRegex(
            VerifierProcessError, "^verifier process: child exit failed$"
        ) as raised:
            adapter.verify(valid_verifier_input())
        self.assertNotIn(canary, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
