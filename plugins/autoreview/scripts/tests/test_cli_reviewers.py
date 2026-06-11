from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest


GATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gate.py")


def run_git(d: str, *args: str) -> None:
    subprocess.run(["git", *args], cwd=d, capture_output=True, text=True, check=True)


def new_repo() -> str:
    d = tempfile.mkdtemp(prefix="ar-reviewers-")
    run_git(d, "init", "-q", "-b", "main")
    run_git(d, "config", "user.email", "t@t")
    run_git(d, "config", "user.name", "t")
    run_git(d, "commit", "--allow-empty", "-q", "-m", "root")
    return d


def write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


class TestReviewersCli(unittest.TestCase):
    def test_reviewers_lists_bundled_and_project_local_profiles(self):
        repo = new_repo()
        write(
            os.path.join(repo, ".agents", "autoreview", "reviewers", "domain.md"),
            """---
name: domain
description: Reviews staged changes for domain-specific invariants.
---

Check staged changes against domain invariants.
""",
        )

        p = subprocess.run(
            ["python3", GATE, "reviewers", "--cwd", repo],
            cwd=repo,
            capture_output=True,
            text=True,
        )

        self.assertEqual(p.returncode, 0, p.stderr)
        payload = json.loads(p.stdout)
        self.assertEqual([r["reviewer"] for r in payload["reviewers"]],
                         ["correctness", "security", "conventions", "domain"])
        self.assertEqual(payload["errors"], [])
        self.assertIn('"reviewer": "domain"', payload["reviewers"][-1]["prompt"])

    def test_reviewers_reports_prompt_load_errors_as_needs_context_results(self):
        repo = new_repo()
        write(
            os.path.join(repo, ".agents", "autoreview", "reviewers", "correctness.md"),
            """---
name: correctness
description: Attempts to override bundled correctness.
---

Override bundled correctness.
""",
        )

        p = subprocess.run(
            ["python3", GATE, "reviewers", "--cwd", repo],
            cwd=repo,
            capture_output=True,
            text=True,
        )

        self.assertEqual(p.returncode, 0, p.stderr)
        payload = json.loads(p.stdout)
        self.assertEqual([e["reviewer"] for e in payload["errors"]], ["correctness"])
        self.assertEqual(payload["errors"][0]["review_result"]["outcome"], "NEEDS_CONTEXT")
        self.assertEqual(payload["errors"][0]["review_result"]["review_error"]["kind"],
                         "duplicate_reviewer")

    def test_reviewers_reports_malformed_profile_without_crashing(self):
        repo = new_repo()
        write(
            os.path.join(repo, ".agents", "autoreview", "reviewers", "broken.md"),
            "no frontmatter here\n",
        )

        p = subprocess.run(
            ["python3", GATE, "reviewers", "--cwd", repo],
            cwd=repo,
            capture_output=True,
            text=True,
        )

        self.assertEqual(p.returncode, 0, p.stderr)
        payload = json.loads(p.stdout)
        self.assertEqual([r["reviewer"] for r in payload["reviewers"]],
                         ["correctness", "security", "conventions"])
        self.assertEqual([e["reviewer"] for e in payload["errors"]], ["broken"])
        self.assertEqual(payload["errors"][0]["kind"], "invalid_prompt")

    def test_reviewers_resolves_cwd_to_git_root_for_project_local_profiles(self):
        repo = new_repo()
        subdir = os.path.join(repo, "src", "app")
        os.makedirs(subdir)
        write(
            os.path.join(repo, ".agents", "autoreview", "reviewers", "domain.md"),
            """---
name: domain
description: Reviews staged changes for domain-specific invariants.
---

Check staged changes against domain invariants.
""",
        )

        p = subprocess.run(
            ["python3", GATE, "reviewers", "--cwd", subdir],
            cwd=repo,
            capture_output=True,
            text=True,
        )

        self.assertEqual(p.returncode, 0, p.stderr)
        payload = json.loads(p.stdout)
        self.assertEqual(payload["repo_root"], os.path.realpath(repo))
        self.assertEqual(payload["reviewers"][-1]["reviewer"], "domain")

    def test_reviewers_reports_discovery_failure_as_needs_context_result(self):
        not_repo = tempfile.mkdtemp(prefix="ar-not-repo-")

        p = subprocess.run(
            ["python3", GATE, "reviewers", "--cwd", not_repo],
            cwd=not_repo,
            capture_output=True,
            text=True,
        )

        self.assertEqual(p.returncode, 0, p.stderr)
        payload = json.loads(p.stdout)
        self.assertEqual(payload["reviewers"], [])
        self.assertEqual(payload["errors"][0]["reviewer"], "reviewer-discovery")
        self.assertEqual(payload["errors"][0]["review_result"]["outcome"], "NEEDS_CONTEXT")
        self.assertEqual(payload["errors"][0]["review_result"]["review_error"]["kind"],
                         "reviewer_discovery_failed")


if __name__ == "__main__":
    unittest.main()
