from __future__ import annotations

import json
import os
import subprocess
import unittest


from tests.helpers import approved_marker, new_repo, stage_nontrivial, write_profile

GATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gate.py")
APPROVED_MARKER = approved_marker()


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
        write_profile(d, "foo")
        code, report = gate_check(d)
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "insufficient")
        self.assertEqual(report["missing_reviewers"], ["foo"])


if __name__ == "__main__":
    unittest.main()
