# Architecture

## Overview

`open-agent-skills` is a multi-agent skills library. Each plugin groups one or more *skills* — self-contained reference documents that compatible coding tools load when a user's question matches the skill's trigger description.

The repository is structured so that one source of truth (`plugins/`) feeds multiple coding agents through tool-specific registries.

```
.agents/
  plugins/
    marketplace.json        # OpenAI Codex registry
.claude-plugin/
  marketplace.json          # Claude Code registry
plugins/
  <plugin-name>/
    .claude-plugin/
      plugin.json           # Claude Code per-plugin manifest
    .codex-plugin/
      plugin.json           # Codex per-plugin manifest
    hooks.json              # (optional) compatibility copy of plugin hooks
    hooks/
      hooks.json            # (optional) primary plugin hooks
    scripts/                # (optional) executable helpers a hook/skill invokes
    agents/
      <id>.md               # (optional) provider-neutral reviewer profiles
    skills/
      <skill-name>/
        SKILL.md            # The skill document (frontmatter + markdown)
AGENTS.md                   # AI coding agent entrypoint
README.md                   # Human-facing project overview
```

### Hooks (plugin component)

A plugin may ship lifecycle hooks. The primary hook file is `hooks/hooks.json`; plugins may also
ship a root-level `hooks.json` compatibility copy when targeting hosts that have used that location.
When both files exist they must stay byte-identical. Hook commands should resolve the plugin install
directory through host-provided plugin-root environment variables with a relative fallback. Any
runtime a hook shells out to, such as `python3`, must be treated as optional and fail open if absent.

## Supported Agents

| Agent | Discovery |
|---|---|
| Claude Code | Reads `.claude-plugin/marketplace.json` and each plugin's `.claude-plugin/plugin.json` |
| OpenAI Codex | Reads `.agents/plugins/marketplace.json` and each plugin's `.codex-plugin/plugin.json` |
| Gemini CLI | Planned. Discovery format and entrypoint to be added when support lands |

When adding support for a new agent, add a new entrypoint or registry file rather than forking shared skill content.

## Plugin Registries

Each registry describes the same `plugins/` tree but uses a different schema to match each tool's expectations.

### Claude Code marketplace (`.claude-plugin/marketplace.json`)

| Field | Purpose |
|---|---|
| `name` | Marketplace identifier |
| `owner` | Marketplace owner metadata (`name`; optional `email`) |
| `plugins[].name` | Plugin identifier (matches directory name) |
| `plugins[].source` | Relative path to the plugin directory |
| `plugins[].description` | Human-readable plugin summary |
| `plugins[].version` | Semantic version |
| `plugins[].author` | Plugin author metadata |

### Claude Code per-plugin manifest (`plugins/<plugin>/.claude-plugin/plugin.json`)

Claude Code resolves marketplace plugins in `strict` mode by default, which expects each plugin directory to contain its own `.claude-plugin/plugin.json`. Skills are auto-discovered from the plugin's `skills/` directory, so the manifest does not enumerate them.

| Field | Purpose |
|---|---|
| `name` | Plugin identifier (matches directory name) |
| `version` | Semantic version |
| `description` | Human-readable plugin summary |
| `author` | Plugin author metadata |

### Codex marketplace (`.agents/plugins/marketplace.json`)

| Field | Purpose |
|---|---|
| `name` | Marketplace identifier |
| `interface.displayName` | Codex marketplace display name |
| `plugins[].name` | Plugin identifier (matches directory name) |
| `plugins[].source` | `{ "source": "local", "path": "./plugins/<plugin>" }` |
| `plugins[].policy` | Codex install and authentication policy |
| `plugins[].category` | Codex marketplace category |

### Codex per-plugin manifest (`plugins/<plugin>/.codex-plugin/plugin.json`)

| Field | Purpose |
|---|---|
| `name`, `version`, `description` | Required package identity metadata |
| `author` | Publisher metadata |
| `skills` | Relative path to the skill directory; currently always `./skills/` |
| `hooks` | Optional relative path to the primary hooks file, such as `./hooks/hooks.json` |
| `interface` | Codex install-surface display metadata |

Every registry and manifest should list the same plugins in the same order unless a tool-specific compatibility issue requires an exception.

## Skill Document Format

Every skill lives in `plugins/<plugin>/skills/<skill-name>/SKILL.md`.

```
---
name: <skill-name>          # Kebab-case; matches the directory name exactly
description: <trigger text> # Multi-sentence description of when a coding tool should use this skill
---

# <Skill Title>

<One-line intro sentence.>

---

## <Major Section>

...

## Anti-Patterns

| Anti-pattern | Problem | Fix |
|---|---|---|
```

### Frontmatter rules

- `name` must exactly match the containing directory name.
- `description` is the primary routing signal — it should enumerate trigger conditions, covered topics, and common user questions that should activate the skill.

### Content conventions

- Sections use `##`; subsections use `###`.
- Code blocks are language-tagged (e.g. `ruby`, `erb`, `bash`, `javascript`, `yaml`).
- Decision matrices and quick-reference tables use a three-column format.
- Every skill ends with an **Anti-Patterns** table (`Anti-pattern | Problem | Fix`).
- Target length: 300–500 lines. Dense and practical; no filler.

## Plugins

### `autoreview`

A deterministic pre-commit review gate. A `PreToolUse` hook on `git commit` runs a zero-LLM Python
gate (`scripts/gate.py`, behind the fail-open `scripts/gate.sh` wrapper) over the staged change.
The gate supports either the hook working directory or a direct `git -C <worktree> commit` target so
autonomous subagents can commit from isolated worktrees without changing shell cwd. Trivial changes
pass silently; non-trivial, sensitive, or hand-resolved-merge changes are blocked (exit 2) with a
directive to run the `autoreview` skill. The skill launches provider-neutral reviewer profiles from
`agents/*.md`, requires strict JSON outcomes, and lets the agent address blocking feedback before
re-committing. A content-keyed pass-marker in the repo's git dir, never committed, records only
approved or non-blocking reviewed outcomes. For explicit worktree targets, the marker is written
with `gate.py mark --cwd <worktree>`. The gate requires `python3` and fails open if it is absent.

| Component | Purpose |
|---|---|
| `scripts/` | `gate.py` (gate + `mark`), `gitcmd.py`/`diffparse.py`/`classify.py`/`markers.py`/`schema.py`/`core.py`/`cli.py` package, `gate.sh` wrapper, tests |
| `hooks.json` + `hooks/hooks.json` | `PreToolUse -> Bash` wiring kept byte-identical for host compatibility |
| `agents/{correctness,security,conventions}.md` | Provider-neutral reviewer profiles that return strict JSON |
| `skills/autoreview/SKILL.md` | Orchestration: gather staged context, launch reviewers, aggregate outcomes, resolve feedback, marker + re-commit |

## Adding a Plugin

1. Create `plugins/<plugin-name>/` with a `skills/` subdirectory.
2. Add `plugins/<plugin-name>/.claude-plugin/plugin.json` (Claude Code per-plugin manifest).
3. Add `plugins/<plugin-name>/.codex-plugin/plugin.json` with `skills` set to `./skills/`.
4. Add an entry to both `.claude-plugin/marketplace.json` and `.agents/plugins/marketplace.json`.
5. Document the plugin in `README.md`.
6. Document the plugin and its skills in this file.

## Adding a Skill

1. Create `plugins/<plugin>/skills/<skill-name>/SKILL.md` following the format above.
2. Update the plugin's skill table in `README.md` and this file.

## Maintenance Guidelines

- Keep skill content agent-neutral. Avoid naming a specific assistant unless the section is an adapter or entrypoint for that assistant.
- When adding support for a new agent, add or update an entrypoint file and document the discovery behavior here.
- When introducing a new convention that depends on a specific agent's discovery mechanism, document that dependency in this file rather than in shared skill bodies.
