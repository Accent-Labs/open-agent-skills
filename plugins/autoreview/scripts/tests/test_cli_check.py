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
    "reviewers": [
        {"reviewer": "correctness", "outcome": "APPROVED"},
        {"reviewer": "security", "outcome": "APPROVED"},
        {"reviewer": "conventions", "outcome": "APPROVED"},
    ],
}


def run(d, *args):
    return subprocess.run(["git", *args], cwd=d, capture_output=True, text=True, check=True)


def new_repo():
    d = tempfile.mkdtemp(prefix="ar-check-")
    run(d, "init", "-q", "-b", "main")
    run(d, "config", "user.email", "t@t")
    run(d, "config", "user.name", "t")
    run(d, "commit", "--allow-empty", "-q", "-m", "root")
    return d


def stage_nontrivial(d):
    with open(os.path.join(d, "src.py"), "w") as fh:
        fh.write("x\n" * 40)
    run(d, "add", "src.py")


def gate_check(d):
    p = subprocess.run(["python3", GATE, "check", "--cwd", d], capture_output=True, text=True)
    return p.returncode, json.loads(p.stdout)


def gate_decide(d):
    payload = json.dumps({"cwd": d, "tool_input": {"command": "git commit -m x"}})
    return subprocess.run(["python3", GATE], input=payload, cwd=d,
                          capture_output=True, text=True).returncode


class TestCheckCli(unittest.TestCase):
    def test_check_reports_none_without_marker(self):
        d = new_repo()
        stage_nontrivial(d)
        code, report = gate_check(d)
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "none")
        self.assertEqual(report["required_reviewers"],
                         ["correctness", "security", "conventions"])

    def test_check_does_not_consume_a_valid_marker(self):
        d = new_repo()
        stage_nontrivial(d)
        subprocess.run(["python3", GATE, "mark", "--cwd", d, "--payload",
                        json.dumps(APPROVED_MARKER)], capture_output=True, text=True, check=True)
        for _ in range(2):  # repeated checks must not consume
            code, report = gate_check(d)
            self.assertEqual(code, 0)
            self.assertEqual(report["status"], "valid")
            self.assertEqual(report["missing_reviewers"], [])
        self.assertEqual(gate_decide(d), 0)  # the gate still finds and consumes the marker
        code, report = gate_check(d)
        self.assertEqual(report["status"], "none")

    def test_check_reports_missing_reviewers_for_stale_marker(self):
        d = new_repo()
        stage_nontrivial(d)
        subprocess.run(["python3", GATE, "mark", "--cwd", d, "--payload",
                        json.dumps(APPROVED_MARKER)], capture_output=True, text=True, check=True)
        # a project-local reviewer appears after the mark (untracked, so identity is unchanged)
        profile_dir = os.path.join(d, ".agents", "autoreview", "reviewers")
        os.makedirs(profile_dir)
        with open(os.path.join(profile_dir, "foo.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nname: foo\ndescription: Reviews staged changes for foo concerns.\n"
                     "---\n\nCheck staged changes for foo concerns.\n")
        code, report = gate_check(d)
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "insufficient")
        self.assertEqual(report["missing_reviewers"], ["foo"])


if __name__ == "__main__":
    unittest.main()
