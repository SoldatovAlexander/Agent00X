from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scripts import measure_r5_worker_token_parity as measure


class _FakeResponse:
    status = 200

    def __init__(self, value):
        self.raw = json.dumps(value, separators=(",", ":")).encode("utf-8")

    def getheader(self, name):
        if name.lower() == "content-type":
            return "application/json"
        if name.lower() == "content-length":
            return str(len(self.raw))
        return None

    def read(self, size):
        return self.raw[:size]


class _FakeConnection:
    calls = []
    fail_at = None
    invalid_at = None

    def __init__(self, host, *, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout

    def request(self, method, path, *, body, headers):
        call = {
            "host": self.host,
            "port": self.port,
            "timeout": self.timeout,
            "method": method,
            "path": path,
            "body": json.loads(body),
            "headers": headers,
        }
        self.calls.append(call)
        if self.fail_at == len(self.calls):
            raise OSError("PRIVATE_FAKE_FAILURE")
        if self.invalid_at == len(self.calls):
            self.response = _FakeResponse({"prompt": "private", "extra": True})
        elif path == "/apply-template":
            self.response = _FakeResponse({"prompt": f"fake-rendered-{len(self.calls)}"})
        else:
            self.response = _FakeResponse({"tokens": [0, 1, 2]})

    def getresponse(self):
        return self.response

    def close(self):
        pass


class R5WorkerTokenParityTests(unittest.TestCase):
    def setUp(self):
        _FakeConnection.calls = []
        _FakeConnection.fail_at = None
        _FakeConnection.invalid_at = None

    def test_success_makes_exact_20_template_then_20_tokenize_calls(self):
        import io

        output = io.StringIO()
        result = measure.run_measurement(_FakeConnection, output)
        self.assertEqual(result, 0)
        self.assertEqual(len(_FakeConnection.calls), 40)
        calls = _FakeConnection.calls
        self.assertEqual([call["path"] for call in calls[:20]], ["/apply-template"] * 20)
        self.assertEqual([call["path"] for call in calls[20:]], ["/tokenize"] * 20)
        self.assertTrue(all(call["host"] == "127.0.0.1" for call in calls))
        self.assertTrue(all(call["port"] == 18080 for call in calls))
        self.assertTrue(all(call["timeout"] == 10 for call in calls))
        self.assertTrue(all(call["method"] == "POST" for call in calls))
        self.assertTrue(all(call["body"]["add_generation_prompt"] is True for call in calls[:20]))
        self.assertTrue(all(call["body"]["add_special"] is False for call in calls[20:]))
        self.assertTrue(all(call["body"]["parse_special"] is True for call in calls[20:]))
        self.assertTrue(all(call["body"]["with_pieces"] is False for call in calls[20:]))
        result_json = json.loads(output.getvalue())
        self.assertEqual(result_json["status"], "COMPLETE")
        self.assertTrue(result_json["eligible"])
        self.assertEqual(result_json["completed_requests"], 40)
        self.assertEqual(len(result_json["scenario_counts"]), 5)
        self.assertNotIn("fake-rendered", output.getvalue())
        self.assertNotIn("PRIVATE_FAKE_FAILURE", output.getvalue())

    def test_first_request_failure_stops_without_retry_and_redacts(self):
        import io

        _FakeConnection.fail_at = 1
        output = io.StringIO()
        result = measure.run_measurement(_FakeConnection, output)
        self.assertEqual(result, 3)
        self.assertEqual(len(_FakeConnection.calls), 1)
        self.assertEqual(
            json.loads(output.getvalue()),
            {"status": "STOPPED", "step": "apply-template", "completed_requests": 0},
        )
        self.assertNotIn("PRIVATE_FAKE_FAILURE", output.getvalue())

    def test_invalid_response_stops_without_later_requests(self):
        import io

        _FakeConnection.invalid_at = 1
        output = io.StringIO()
        result = measure.run_measurement(_FakeConnection, output)
        self.assertEqual(result, 3)
        self.assertEqual(len(_FakeConnection.calls), 1)
        self.assertEqual(
            json.loads(output.getvalue()),
            {"status": "STOPPED", "step": "apply-template", "completed_requests": 1},
        )
        self.assertNotIn("private", output.getvalue())


if __name__ == "__main__":
    unittest.main()
