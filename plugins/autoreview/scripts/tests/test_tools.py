from __future__ import annotations
import unittest
from autoreview import tools as t


class TestTools(unittest.TestCase):
    def test_claude(self):
        d = t.detect_tool({"CLAUDECODE": "1"})
        self.assertEqual(d["id"], "claude-code")
        self.assertTrue(d["supportsCustomSubagents"])

    def test_codex(self):
        self.assertEqual(t.detect_tool({"CODEX_THREAD_ID": "019e"})["id"], "codex")
        self.assertEqual(t.detect_tool({"CODEX_SHELL": "1"})["id"], "codex")
        self.assertFalse(t.detect_tool({"CODEX_CI": "1"})["supportsCustomSubagents"])

    def test_generic(self):
        self.assertEqual(t.detect_tool({})["id"], "generic")

    def test_matches(self):
        self.assertTrue(t.matches_detect({"env": "CLAUDECODE", "equals": "1"}, {"CLAUDECODE": "1"}))
        self.assertFalse(t.matches_detect({"env": "CLAUDECODE", "equals": "1"}, {"CLAUDECODE": "0"}))
        self.assertTrue(t.matches_detect({"anyEnv": ["A", "B"]}, {"B": "y"}))
        self.assertFalse(t.matches_detect({"anyEnv": ["A", "B"]}, {}))


if __name__ == "__main__":
    unittest.main()
