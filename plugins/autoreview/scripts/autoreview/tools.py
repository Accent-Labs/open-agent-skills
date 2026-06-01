from __future__ import annotations
import json
import os
from typing import Optional

# supportsCustomSubagents decides how the skill spawns reviewers:
#   True  -> native agents/<id>.md subagents by name (Claude Code)
#   False -> read agents/<id>.md, spawn a generic/worker subagent with the body inline
TOOLS = [
    {"id": "claude-code", "name": "Claude Code", "detect": {"env": "CLAUDECODE", "equals": "1"},
     "supportsCustomSubagents": True, "pluginRootEnv": "CLAUDE_PLUGIN_ROOT"},
    {"id": "codex", "name": "OpenAI Codex", "detect": {"anyEnv": ["CODEX_THREAD_ID", "CODEX_SHELL", "CODEX_CI"]},
     "supportsCustomSubagents": False, "pluginRootEnv": "PLUGIN_ROOT"},
    {"id": "gemini", "name": "Gemini CLI", "detect": {"anyEnv": ["GEMINI_CLI", "GEMINI_CLI_VERSION"]},
     "supportsCustomSubagents": False, "pluginRootEnv": "PLUGIN_ROOT"},
]
GENERIC_TOOL = {"id": "generic", "name": "Generic", "detect": None,
                "supportsCustomSubagents": False, "pluginRootEnv": "PLUGIN_ROOT"}


def matches_detect(detect: Optional[dict], env) -> bool:
    if not detect:
        return False
    if "env" in detect:
        v = env.get(detect["env"])
        if "equals" in detect:
            return v == detect["equals"]
        return v not in (None, "")
    if "anyEnv" in detect:
        return any(env.get(k) not in (None, "") for k in detect["anyEnv"])
    return False


def detect_tool(env=None) -> dict:
    env = os.environ if env is None else env
    for tool in TOOLS:
        if matches_detect(tool["detect"], env):
            return tool
    return GENERIC_TOOL


if __name__ == "__main__":
    print(json.dumps(detect_tool(), indent=2))
