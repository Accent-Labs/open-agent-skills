from __future__ import annotations
import json
import os
import tempfile
import time
import unittest
from autoreview import markers as m


class TestMarkers(unittest.TestCase):
    def test_roundtrip_consume(self):
        d = tempfile.mkdtemp()
        f = m.marker_path(d, "abc")
        m.write(f, {"outcome": "APPROVED", "counts": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
                    "feedback": [], "reviewers": [{"reviewer": "correctness", "outcome": "APPROVED"}]})
        self.assertEqual(m.read_with_payload(f)[0], "valid")
        m.consume(f)
        self.assertFalse(os.path.exists(f))
        self.assertEqual(m.read_with_payload(f)[0], "none")

    def test_malformed_quarantined(self):
        d = tempfile.mkdtemp()
        f = m.marker_path(d, "xyz")
        with open(f, "w") as fh:
            fh.write("{ not json")
        self.assertEqual(m.read_with_payload(f)[0], "invalid")
        self.assertTrue(os.path.exists(f + ".invalid"))

    def test_version_expiry(self):
        d = tempfile.mkdtemp()
        f1 = m.marker_path(d, "v")
        with open(f1, "w") as fh:
            fh.write(json.dumps({"version": "bogus", "created": int(time.time() * 1000)}))
        self.assertEqual(m.read_with_payload(f1)[0], "invalid")
        f2 = m.marker_path(d, "e")
        with open(f2, "w") as fh:
            fh.write(json.dumps({"version": m.MARKER_VERSION, "created": 1}))
        self.assertEqual(m.read_with_payload(f2)[0], "invalid")

    def test_sanitize_merge_identity(self):
        d = tempfile.mkdtemp()
        self.assertNotIn(":", os.path.basename(m.marker_path(d, "aaa:bbb:ccc")))

    def test_semantically_corrupt_payload_fails_closed(self):
        d = tempfile.mkdtemp()
        f1 = m.marker_path(d, "badcreated")
        with open(f1, "w") as fh:
            fh.write(json.dumps({"version": m.MARKER_VERSION, "created": "not-a-number"}))
        self.assertEqual(m.read_with_payload(f1)[0], "invalid")  # not fail-open
        self.assertTrue(os.path.exists(f1 + ".invalid"))
        f2 = m.marker_path(d, "notdict")
        with open(f2, "w") as fh:
            fh.write(json.dumps([1, 2, 3]))  # valid JSON, not an object
        self.assertEqual(m.read_with_payload(f2)[0], "invalid")
        self.assertTrue(os.path.exists(f2 + ".invalid"))

    def test_non_authorizing_payload_fails_closed(self):
        d = tempfile.mkdtemp()
        for ident, payload in (
            ("empty", {}),
            ("legacy-pass", {"verdict": "PASS"}),
            ("legacy-fail", {"verdict": "FAIL"}),
            ("needs-context", {"outcome": "NEEDS_CONTEXT",
                               "counts": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
                               "feedback": [], "reviewers": []}),
            ("changes", {"outcome": "CHANGES_REQUESTED",
                         "counts": {"critical": 0, "high": 1, "medium": 0, "low": 0, "info": 0},
                         "feedback": [{"severity": "high", "path": "x", "line": 1, "title": "x",
                                       "impact": "x", "evidence": "x", "recommendation": "x",
                                       "blocking": True}],
                         "reviewers": []}),
        ):
            f = m.marker_path(d, ident)
            body = dict(payload)
            body["version"] = m.MARKER_VERSION
            body["created"] = int(time.time() * 1000)
            with open(f, "w") as fh:
                fh.write(json.dumps(body))
            self.assertEqual(m.read_with_payload(f)[0], "invalid", ident)


if __name__ == "__main__":
    unittest.main()
