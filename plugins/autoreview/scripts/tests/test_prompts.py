from __future__ import annotations

import os
import tempfile
import unittest

from autoreview import prompts


def write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


class TestReviewerPrompts(unittest.TestCase):
    def test_discovers_bundled_reviewers_without_project_local_directory(self):
        repo = tempfile.mkdtemp(prefix="ar-prompts-")

        profiles, errors = prompts.discover_reviewer_profiles(repo)

        self.assertEqual([p.reviewer for p in profiles], ["correctness", "security", "conventions"])
        self.assertEqual([p.source for p in profiles], ["bundled", "bundled", "bundled"])
        self.assertEqual(errors, [])

    def test_discovers_project_local_reviewers_after_bundled_reviewers(self):
        repo = tempfile.mkdtemp(prefix="ar-prompts-")
        write(
            os.path.join(repo, ".agents", "autoreview", "reviewers", "domain.md"),
            """---
name: domain
description: Reviews staged changes for domain-specific invariants.
---

Check staged changes against billing domain invariants.
""",
        )
        write(
            os.path.join(repo, ".agents", "autoreview", "reviewers", "api-contracts.md"),
            """---
name: api-contracts
description: Reviews staged changes for public API compatibility.
---

Check staged changes for public API compatibility.
""",
        )

        profiles, errors = prompts.discover_reviewer_profiles(repo)

        self.assertEqual(
            [(p.reviewer, p.source) for p in profiles],
            [
                ("correctness", "bundled"),
                ("security", "bundled"),
                ("conventions", "bundled"),
                ("api-contracts", "project_local"),
                ("domain", "project_local"),
            ],
        )
        self.assertEqual(errors, [])

    def test_rejects_project_local_duplicate_reviewer_id_without_overriding_bundled(self):
        repo = tempfile.mkdtemp(prefix="ar-prompts-")
        write(
            os.path.join(repo, ".agents", "autoreview", "reviewers", "correctness.md"),
            """---
name: correctness
description: Attempts to override the bundled correctness reviewer.
---

Override the bundled correctness reviewer.
""",
        )

        profiles, errors = prompts.discover_reviewer_profiles(repo)

        self.assertEqual([p.reviewer for p in profiles], ["correctness", "security", "conventions"])
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].reviewer, "correctness")
        self.assertEqual(errors[0].kind, "duplicate_reviewer")
        self.assertIn("already defined", errors[0].message)

    def test_rejects_malformed_project_local_reviewers_as_prompt_errors(self):
        repo = tempfile.mkdtemp(prefix="ar-prompts-")
        write(
            os.path.join(repo, ".agents", "autoreview", "reviewers", "bad.md"),
            """---
name: other
description: Name does not match the filename.
---

Review something.
""",
        )

        _profiles, errors = prompts.discover_reviewer_profiles(repo)

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].reviewer, "bad")
        self.assertEqual(errors[0].kind, "invalid_prompt")
        self.assertIn("frontmatter name", errors[0].message)
        self.assertEqual(errors[0].to_reviewer_result()["outcome"], "NEEDS_CONTEXT")

    def test_rejects_unsafe_project_local_reviewer_ids(self):
        repo = tempfile.mkdtemp(prefix="ar-prompts-")
        write(
            os.path.join(repo, ".agents", "autoreview", "reviewers", "Bad.md"),
            """---
name: Bad
description: Uses an unsafe reviewer id.
---

Review something.
""",
        )

        _profiles, errors = prompts.discover_reviewer_profiles(repo)

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].reviewer, "Bad")
        self.assertEqual(errors[0].kind, "invalid_prompt")
        self.assertIn("reviewer filename", errors[0].message)

    def test_assembled_prompt_combines_persona_with_shared_response_contract(self):
        repo = tempfile.mkdtemp(prefix="ar-prompts-")
        write(
            os.path.join(repo, ".agents", "autoreview", "reviewers", "domain.md"),
            """---
name: domain
description: Reviews staged changes for domain-specific invariants.
---

Check staged changes against billing domain invariants.
""",
        )
        profiles, _errors = prompts.discover_reviewer_profiles(repo)
        domain = next(p for p in profiles if p.reviewer == "domain")

        assembled = prompts.assemble_reviewer_prompt(domain)

        self.assertIn("Check staged changes against billing domain invariants.", assembled)
        self.assertIn('"reviewer": "domain"', assembled)
        self.assertIn('"outcome": "APPROVED"', assembled)
        self.assertIn('"feedback": []', assembled)
        self.assertIn("CHANGES_REQUESTED", assembled)


if __name__ == "__main__":
    unittest.main()
