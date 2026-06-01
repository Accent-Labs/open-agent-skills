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
        m.write(f, {"verdict": "PASS_WITH_ISSUES"})
        self.assertEqual(m.read(f), "valid")
        m.consume(f)
        self.assertFalse(os.path.exists(f))
        self.assertEqual(m.read(f), "none")

    def test_malformed_quarantined(self):
        d = tempfile.mkdtemp()
        f = m.marker_path(d, "xyz")
        open(f, "w").write("{ not json")
        self.assertEqual(m.read(f), "invalid")
        self.assertTrue(os.path.exists(f + ".invalid"))

    def test_version_expiry(self):
        d = tempfile.mkdtemp()
        f1 = m.marker_path(d, "v")
        open(f1, "w").write(json.dumps({"version": "bogus", "created": int(time.time() * 1000)}))
        self.assertEqual(m.read(f1), "invalid")
        f2 = m.marker_path(d, "e")
        open(f2, "w").write(json.dumps({"version": m.MARKER_VERSION, "created": 1}))
        self.assertEqual(m.read(f2), "invalid")

    def test_sanitize_merge_identity(self):
        d = tempfile.mkdtemp()
        self.assertNotIn(":", os.path.basename(m.marker_path(d, "aaa:bbb:ccc")))

    def test_semantically_corrupt_payload_fails_closed(self):
        d = tempfile.mkdtemp()
        f1 = m.marker_path(d, "badcreated")
        with open(f1, "w") as fh:
            fh.write(json.dumps({"version": m.MARKER_VERSION, "created": "not-a-number"}))
        self.assertEqual(m.read(f1), "invalid")  # not fail-open
        self.assertTrue(os.path.exists(f1 + ".invalid"))
        f2 = m.marker_path(d, "notdict")
        with open(f2, "w") as fh:
            fh.write(json.dumps([1, 2, 3]))  # valid JSON, not an object
        self.assertEqual(m.read(f2), "invalid")
        self.assertTrue(os.path.exists(f2 + ".invalid"))


if __name__ == "__main__":
    unittest.main()
