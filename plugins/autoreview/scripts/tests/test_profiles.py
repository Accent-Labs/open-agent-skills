from __future__ import annotations
import os
import re
import unittest

from autoreview import prompts


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AGENTS = os.path.join(ROOT, "agents")
SKILL = os.path.join(ROOT, "skills", "autoreview", "SKILL.md")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def parse_frontmatter(text):
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 5:]
    data = {}
    for line in raw.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            data[k.strip()] = v.strip()
    return data, body


class TestProfiles(unittest.TestCase):
    def test_expected_provider_neutral_profiles(self):
        names = sorted(n for n in os.listdir(AGENTS) if n.endswith(".md"))
        self.assertEqual(names, ["conventions.md", "correctness.md", "security.md"])
        for filename in names:
            text = read(os.path.join(AGENTS, filename))
            frontmatter, body = parse_frontmatter(text)
            stem = filename[:-3]
            self.assertEqual(frontmatter.get("name"), stem)
            self.assertNotIn("model", frontmatter)
            self.assertNotIn("tools", frontmatter)
            self.assertIn("Quality bar:", body)
            self.assertNotRegex(body, r"\bAPPROVED\b")
            self.assertNotRegex(body, r"\bCHANGES_REQUESTED\b")
            self.assertNotRegex(body, r"\bCOMMENTED\b")
            self.assertNotRegex(body, r"\bNEEDS_CONTEXT\b")
            self.assertNotRegex(body, r"\bJSON\b")
            self.assertNotRegex(body, r"\bClaude\b|\bCodex\b|\bGemini\b|native subagent|Read tool")

    def test_skill_is_provider_neutral(self):
        body = parse_frontmatter(read(SKILL))[1]
        self.assertNotRegex(body, r"supportsCustomSubagents|detect_tool\.py|native subagent")
        self.assertNotRegex(body, r"\bClaude Code\b|\bOpenAI Codex\b|\bGemini\b")
        self.assertIn("git show :path", body)
        self.assertIn("NEEDS_CONTEXT", body)

    def test_skill_requires_commit_message_summary_for_addressed_feedback(self):
        body = parse_frontmatter(read(SKILL))[1]
        self.assertRegex(body, r"(?is)commit message.*feedback.*fixes")
        self.assertRegex(body, r"(?is)feedback.*fixes.*commit message")

    def test_assembled_prompts_include_response_contract_without_placeholder_enums(self):
        for filename in sorted(n for n in os.listdir(AGENTS) if n.endswith(".md")):
            profile = prompts.load_bundled_profile(os.path.join(AGENTS, filename))
            body = prompts.assemble_reviewer_prompt(profile)
            self.assertNotRegex(body, r'"outcome":\s*"[^"]*\|')
            self.assertNotRegex(body, r'"severity":\s*"[^"]*\|')
            self.assertRegex(body, r"(?is)raw JSON.*no Markdown fences|no Markdown fences.*raw JSON")
        skill_body = parse_frontmatter(read(SKILL))[1]
        self.assertNotRegex(skill_body, r'"outcome":\s*"[^"]*\|')
        self.assertNotRegex(skill_body, r'"severity":\s*"[^"]*\|')

    def test_skill_launches_workers_by_reviewer_profile(self):
        body = parse_frontmatter(read(SKILL))[1]
        self.assertRegex(body, r"one isolated worker per reviewer profile")
        self.assertNotRegex(body, r"one isolated worker per file")

    def test_skill_validation_uses_non_consuming_check(self):
        body = parse_frontmatter(read(SKILL))[1]
        self.assertRegex(body, r"gate\.py\"? check")
        self.assertRegex(body, r"(?is)consum\w+.*valid marker|valid marker.*consum\w+")

    def test_skill_requires_marker_to_cover_discovered_reviewers(self):
        body = parse_frontmatter(read(SKILL))[1]
        self.assertRegex(body, r"(?is)reviewers.*must.*every discovered reviewer")

    def test_skill_documents_project_local_trust_model(self):
        body = parse_frontmatter(read(SKILL))[1]
        self.assertRegex(body, r"(?is)project-local.*repo-controlled")

    def test_profiles_define_non_overlapping_roles(self):
        for filename in sorted(n for n in os.listdir(AGENTS) if n.endswith(".md")):
            body = parse_frontmatter(read(os.path.join(AGENTS, filename)))[1]
            self.assertRegex(body, r"Do not duplicate")


if __name__ == "__main__":
    unittest.main()
