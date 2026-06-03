from __future__ import annotations
import os
import subprocess
import tempfile
import unittest

WRAP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gate.sh")


def run(payload, env=None):
    e = dict(os.environ)
    e.update(env or {})
    p = subprocess.run(["/bin/sh", WRAP], input=payload, capture_output=True, text=True, env=e)
    return p.returncode, p.stderr


def git(d, *args):
    return subprocess.run(["git", *args], cwd=d, capture_output=True, text=True, check=True)


def new_repo():
    d = tempfile.mkdtemp(prefix="ar-wrap-")
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    git(d, "commit", "--allow-empty", "-q", "-m", "root")
    return d


def stage(d, rel, lines):
    path = os.path.join(d, rel)
    os.makedirs(os.path.dirname(path) or d, exist_ok=True)
    with open(path, "w") as fh:
        fh.write("x\n" * lines)
    git(d, "add", rel)


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

    def test_wrapper_preserves_review_block_exit_2(self):
        d = new_repo()
        stage(d, "src/a.py", 40)
        code, err = run('{"cwd":"%s","tool_input":{"command":"git commit -m x"}}' % d)
        self.assertEqual(code, 2)
        self.assertRegex(err, r"(?i)autoreview required")

    def test_wrapper_allows_trivial_change(self):
        d = new_repo()
        stage(d, "README.md", 40)
        code, err = run('{"cwd":"%s","tool_input":{"command":"git commit -m x"}}' % d)
        self.assertEqual(code, 0, err)

    def test_wrapper_fail_opens_malformed_stdin(self):
        code, err = run("{not json")
        self.assertEqual(code, 0)
        self.assertRegex(err, r"(?i)allowing")

    def test_wrapper_normalizes_non_block_python_failures(self):
        root = tempfile.mkdtemp(prefix="ar-fake-root-")
        scripts = os.path.join(root, "scripts")
        os.makedirs(scripts)
        fake_gate = os.path.join(scripts, "gate.py")
        with open(fake_gate, "w") as fh:
            fh.write("import sys\nsys.exit(7)\n")
        code, err = run('{"cwd":"%s","tool_input":{"command":"git commit -m x"}}' % os.getcwd(),
                        {"PLUGIN_ROOT": root})
        self.assertEqual(code, 0)
        self.assertRegex(err, r"gate exited 7")


if __name__ == "__main__":
    unittest.main()
