from __future__ import annotations
import json
import os
import subprocess
import tempfile
import unittest


GATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gate.py")
BUNDLED = ("correctness", "security", "conventions")


def approved_marker(*reviewers):
    ids = reviewers or BUNDLED
    return {
        "outcome": "APPROVED",
        "counts": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
        "feedback": [],
        "reviewers": [{"reviewer": r, "outcome": "APPROVED"} for r in ids],
    }


APPROVED_MARKER = approved_marker()


def profile(reviewer):
    return """---
name: %s
description: Reviews staged changes for %s concerns.
---

Check staged changes for %s concerns.
""" % (reviewer, reviewer, reviewer)


def write_profile(repo, reviewer, content=None):
    d = os.path.join(repo, ".agents", "autoreview", "reviewers")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, reviewer + ".md"), "w", encoding="utf-8") as fh:
        fh.write(content if content is not None else profile(reviewer))


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

    def test_mark_rejects_payload_missing_bundled_reviewer(self):
        d = new_repo()
        with open(os.path.join(d, "src.py"), "w") as fh:
            fh.write("x\n" * 40)
        run(d, "add", "src.py")
        p = subprocess.run(
            ["python3", GATE, "mark", "--payload", json.dumps(approved_marker("correctness"))],
            cwd=d, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertRegex(p.stderr, r"missing required reviewer")
        self.assertIn("security", p.stderr)
        self.assertIn("conventions", p.stderr)
        self.assertEqual(marker_names(d), [])

    def test_mark_rejects_payload_missing_project_local_reviewer(self):
        d = new_repo()
        write_profile(d, "foo")
        write_profile(d, "bar")
        with open(os.path.join(d, "src.py"), "w") as fh:
            fh.write("x\n" * 40)
        run(d, "add", "src.py")
        p = subprocess.run(
            ["python3", GATE, "mark", "--payload", json.dumps(approved_marker(*BUNDLED, "bar"))],
            cwd=d, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertRegex(p.stderr, r"missing required reviewer\(s\): foo;")
        self.assertEqual(marker_names(d), [])

    def test_mark_accepts_payload_covering_bundled_and_project_local(self):
        d = new_repo()
        write_profile(d, "foo")
        write_profile(d, "bar")
        with open(os.path.join(d, "src.py"), "w") as fh:
            fh.write("x\n" * 40)
        run(d, "add", "src.py")
        p = subprocess.run(
            ["python3", GATE, "mark", "--payload",
             json.dumps(approved_marker(*BUNDLED, "bar", "foo"))],
            cwd=d, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("marker written", p.stdout)
        self.assertEqual(len(marker_names(d)), 1)

    def test_mark_rejects_when_project_local_profile_is_malformed(self):
        d = new_repo()
        write_profile(d, "broken", "no frontmatter here\n")
        with open(os.path.join(d, "src.py"), "w") as fh:
            fh.write("x\n" * 40)
        run(d, "add", "src.py")
        p = subprocess.run(
            ["python3", GATE, "mark", "--payload",
             json.dumps(approved_marker(*BUNDLED, "broken"))],
            cwd=d, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertRegex(p.stderr, r"invalid project-local reviewer profile")
        self.assertIn("broken", p.stderr)
        self.assertEqual(marker_names(d), [])

    def test_mark_rejects_when_project_local_profile_duplicates_bundled_id(self):
        d = new_repo()
        write_profile(d, "correctness")
        with open(os.path.join(d, "src.py"), "w") as fh:
            fh.write("x\n" * 40)
        run(d, "add", "src.py")
        p = subprocess.run(
            ["python3", GATE, "mark", "--payload", json.dumps(approved_marker())],
            cwd=d, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertRegex(p.stderr, r"invalid project-local reviewer profile")
        self.assertIn("already defined", p.stderr)
        self.assertEqual(marker_names(d), [])

    def test_mark_enforces_project_local_reviewers_in_linked_worktree(self):
        d = new_repo()
        write_profile(d, "foo")
        run(d, "add", ".agents")
        run(d, "commit", "-q", "-m", "add local reviewer")
        wt = tempfile.mkdtemp(prefix="ar-wt-")
        os.rmdir(wt)
        run(d, "worktree", "add", "-q", wt, "-b", "wt-branch")
        with open(os.path.join(wt, "src.py"), "w") as fh:
            fh.write("x\n" * 40)
        run(wt, "add", "src.py")

        p = subprocess.run(
            ["python3", GATE, "mark", "--cwd", wt, "--payload", json.dumps(approved_marker())],
            cwd=d, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertRegex(p.stderr, r"missing required reviewer")
        self.assertIn("foo", p.stderr)

        p = subprocess.run(
            ["python3", GATE, "mark", "--cwd", wt, "--payload",
             json.dumps(approved_marker(*BUNDLED, "foo"))],
            cwd=d, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("marker written", p.stdout)


if __name__ == "__main__":
    unittest.main()
