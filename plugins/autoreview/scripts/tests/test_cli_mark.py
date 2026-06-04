from __future__ import annotations
import json
import os
import subprocess
import tempfile
import unittest


GATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gate.py")
APPROVED_MARKER = {
    "outcome": "APPROVED",
    "counts": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
    "feedback": [],
    "reviewers": [{"reviewer": "correctness", "outcome": "APPROVED"}],
}


def run(d, *args):
    return subprocess.run(["git", *args], cwd=d, capture_output=True, text=True, check=True)


def new_repo():
    d = tempfile.mkdtemp(prefix="ar-mark-")
    run(d, "init", "-q", "-b", "main")
    run(d, "config", "user.email", "t@t")
    run(d, "config", "user.name", "t")
    run(d, "commit", "--allow-empty", "-q", "-m", "root")
    return d


def marker_names(d):
    p = subprocess.run(["git", "rev-parse", "--git-path", "autoreview"], cwd=d,
                       capture_output=True, text=True, check=True)
    marker_dir = os.path.join(d, p.stdout.strip())
    return os.listdir(marker_dir) if os.path.isdir(marker_dir) else []


class TestMarkCli(unittest.TestCase):
    def test_invalid_mark_payload_does_not_write_marker(self):
        d = new_repo()
        with open(os.path.join(d, "src.py"), "w") as fh:
            fh.write("x\n" * 40)
        run(d, "add", "src.py")
        for payload in ("{not json", json.dumps({"verdict": "FAIL"})):
            p = subprocess.run(["python3", GATE, "mark", "--payload", payload],
                               cwd=d, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0)
            self.assertRegex(p.stderr, r"(?i)mark failed|invalid")
            self.assertEqual(marker_names(d), [])

    def test_mark_can_target_git_dash_c_worktree(self):
        caller = new_repo()
        target = new_repo()
        with open(os.path.join(target, "src.py"), "w") as fh:
            fh.write("x\n" * 40)
        run(target, "add", "src.py")

        p = subprocess.run(
            ["python3", GATE, "mark", "--cwd", target, "--payload", json.dumps(APPROVED_MARKER)],
            cwd=caller,
            capture_output=True,
            text=True,
        )

        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(marker_names(caller), [])
        self.assertEqual(len(marker_names(target)), 1)


if __name__ == "__main__":
    unittest.main()
