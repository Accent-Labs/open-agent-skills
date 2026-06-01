from __future__ import annotations
import os
import re
import unittest


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
            self.assertRegex(body, r"\bAPPROVED\b")
            self.assertRegex(body, r"\bCHANGES_REQUESTED\b")
            self.assertRegex(body, r"\bCOMMENTED\b")
            self.assertRegex(body, r"\bNEEDS_CONTEXT\b")
            self.assertRegex(body, r"\bJSON\b")
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


if __name__ == "__main__":
    unittest.main()
