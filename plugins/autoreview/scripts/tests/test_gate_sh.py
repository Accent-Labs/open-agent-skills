from __future__ import annotations
import os
import subprocess
import unittest

WRAP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gate.sh")


def run(payload, env=None):
    e = dict(os.environ)
    e.update(env or {})
    p = subprocess.run(["/bin/sh", WRAP], input=payload, capture_output=True, text=True, env=e)
    return p.returncode, p.stderr


class TestWrapper(unittest.TestCase):
    def test_allows_non_commit(self):
        code, _ = run('{"cwd":"%s","tool_input":{"command":"ls -la"}}' % os.getcwd())
        self.assertEqual(code, 0)

    def test_fail_open_when_python_missing(self):
        # AUTOREVIEW_NO_PY=1 makes the wrapper pretend python3 is absent (deterministic test hook).
        code, err = run('{"cwd":"%s","tool_input":{"command":"git commit -m x"}}' % os.getcwd(),
                        {"AUTOREVIEW_NO_PY": "1"})
        self.assertEqual(code, 0)
        self.assertRegex(err, r"(?i)autoreview")


if __name__ == "__main__":
    unittest.main()
