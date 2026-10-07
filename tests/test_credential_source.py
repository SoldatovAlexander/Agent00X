from __future__ import annotations

import unittest
from collections.abc import Mapping
from pathlib import Path
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app_contracts.credential_source import (
    CredentialSourceError,
    ProcessEnvironmentCredentialSource,
    TerminalPromptCredentialSource,
)


SECRET = "synthetic-token-do-not-leak"


class RecordingMapping(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lookups: list[str] = []

    def __getitem__(self, name):
        self.lookups.append(name)
        return super().__getitem__(name)


class BrokenMapping(Mapping):
    def __iter__(self):
        return iter(("AI_PROCESS_API",))

    def __len__(self):
        return 1

    def __getitem__(self, _name):
        raise RuntimeError(SECRET)


class ProcessEnvironmentCredentialSourceTests(unittest.TestCase):
    def test_construction_is_lazy_and_call_reads_only_the_named_value(self):
        environment = RecordingMapping(
            {"AI_PROCESS_API": SECRET, "OTHER_TOKEN": "unrelated-secret"}
        )
        original = dict(environment)
        source = ProcessEnvironmentCredentialSource(environment, "AI_PROCESS_API")
        self.assertEqual(environment.lookups, [])
        self.assertEqual(source(), SECRET)
        self.assertEqual(environment.lookups, ["AI_PROCESS_API"])
        self.assertEqual(dict(environment), original)

    def test_safe_diagnostics_do_not_expose_mapping_or_credential_values(self):
        source = ProcessEnvironmentCredentialSource(
            {"AI_PROCESS_API": SECRET, "OTHER_TOKEN": "unrelated-secret"},
            "AI_PROCESS_API",
        )
        diagnostic = repr(source) + str(source)
        self.assertNotIn(SECRET, diagnostic)
        self.assertNotIn("unrelated-secret", diagnostic)
        self.assertNotIn("AI_PROCESS_API", diagnostic)

    def test_missing_and_malformed_values_have_payload_free_errors(self):
        for environment, name in (
            ({}, "AI_PROCESS_API"),
            ({"AI_PROCESS_API": ""}, "AI_PROCESS_API"),
            ({"AI_PROCESS_API": " " + SECRET}, "AI_PROCESS_API"),
            ({"AI_PROCESS_API": SECRET + "\n"}, "AI_PROCESS_API"),
            ({"AI_PROCESS_API": 42}, "AI_PROCESS_API"),
        ):
            with self.subTest(environment=environment):
                source = ProcessEnvironmentCredentialSource(environment, name)
                with self.assertRaises(CredentialSourceError) as raised:
                    source()
                self.assertNotIn(SECRET, str(raised.exception))

    def test_underlying_lookup_error_is_redacted(self):
        source = ProcessEnvironmentCredentialSource(BrokenMapping(), "AI_PROCESS_API")
        with self.assertRaises(CredentialSourceError) as raised:
            source()
        self.assertEqual(
            str(raised.exception), "credential source: value is unavailable"
        )
        self.assertNotIn(SECRET, repr(raised.exception))

    def test_invalid_configuration_is_rejected_without_reading(self):
        for environment, name in (
            (None, "AI_PROCESS_API"),
            ({}, "AI-PROCESS-API"),
            ({}, "1TOKEN"),
            ({}, ""),
        ):
            with self.subTest(name=name):
                with self.assertRaisesRegex(
                    CredentialSourceError,
                    "^credential source: configuration is invalid$",
                ):
                    ProcessEnvironmentCredentialSource(environment, name)


class TerminalPromptCredentialSourceTests(unittest.TestCase):
    def test_hidden_input_is_lazy_and_diagnostics_are_opaque(self):
        import getpass

        source = TerminalPromptCredentialSource()
        with mock.patch("getpass.getpass", return_value=SECRET) as reader:
            self.assertEqual(reader.call_count, 0)
            self.assertEqual(source(), SECRET)
            reader.assert_called_once_with("API credential (input hidden): ")
        self.assertEqual(
            repr(source), "TerminalPromptCredentialSource(value='opaque')"
        )
        self.assertNotIn(SECRET, repr(source) + str(source))

    def test_input_failures_and_malformed_values_are_redacted(self):
        source = TerminalPromptCredentialSource()
        with mock.patch("getpass.getpass", side_effect=RuntimeError(SECRET)):
            with self.assertRaises(CredentialSourceError) as raised:
                source()
        self.assertEqual(
            str(raised.exception), "credential source: secure input unavailable"
        )
        self.assertNotIn(SECRET, repr(raised.exception))

        for value in ("", "  " + SECRET, SECRET + "\n", None, 12):
            with self.subTest(value=type(value).__name__):
                source = TerminalPromptCredentialSource()
                with mock.patch("getpass.getpass", return_value=value):
                    with self.assertRaisesRegex(
                        CredentialSourceError,
                        "^credential source: value is invalid$",
                    ):
                        source()
                self.assertNotIn(SECRET, str(source))

    def test_getpass_echo_fallback_is_rejected(self):
        import getpass

        def insecure_fallback(_prompt):
            import warnings

            warnings.warn("echo may be enabled", getpass.GetPassWarning)
            return SECRET

        source = TerminalPromptCredentialSource()
        with mock.patch("getpass.getpass", side_effect=insecure_fallback):
            with self.assertRaisesRegex(
                CredentialSourceError,
                "^credential source: secure input unavailable$",
            ) as raised:
                source()
        self.assertNotIn(SECRET, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
