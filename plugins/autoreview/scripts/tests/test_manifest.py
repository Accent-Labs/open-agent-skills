from __future__ import annotations
import json
import os
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TestManifestAndHooks(unittest.TestCase):
    def test_hook_files_stay_byte_identical(self):
        root_hook = read(os.path.join(ROOT, "hooks.json"))
        nested_hook = read(os.path.join(ROOT, "hooks", "hooks.json"))
        self.assertEqual(root_hook, nested_hook)

    def test_hook_contract_points_at_gate_wrapper(self):
        hooks = json.loads(read(os.path.join(ROOT, "hooks", "hooks.json")))
        group = hooks["hooks"]["PreToolUse"][0]
        handler = group["hooks"][0]
        self.assertEqual(group["matcher"], "Bash")
        self.assertEqual(handler["type"], "command")
        self.assertIn("gate.sh", handler["command"])
        self.assertEqual(handler["timeout"], 60)

    def test_codex_manifest_declares_skills_and_hooks(self):
        manifest = json.loads(read(os.path.join(ROOT, ".codex-plugin", "plugin.json")))
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertEqual(manifest["hooks"], "./hooks/hooks.json")

    def test_planning_spikes_file_is_not_shipped(self):
        self.assertFalse(os.path.exists(os.path.join(ROOT, "SPIKES.md")))


if __name__ == "__main__":
    unittest.main()
