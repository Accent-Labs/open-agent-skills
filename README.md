# open-agent-skills

An open-source library of plugins and skills for AI coding agents.

Each plugin groups one or more **skills** — self-contained reference documents that compatible coding agents load on demand when a user's question matches the skill's trigger description. Skills are agent-neutral by design: the same skill source feeds multiple tools through tool-specific registries.

## Supported Agents

| Agent | Status | Discovery |
|---|---|---|
| Claude Code | Supported | Reads `.claude-plugin/marketplace.json` and each plugin's `.claude-plugin/plugin.json` |
| OpenAI Codex | Supported | Reads `.agents/plugins/marketplace.json` and each plugin's `.codex-plugin/plugin.json` |
| Gemini CLI | Planned | Discovery format TBD |

The repository is intentionally structured so that adding a new agent means adding a new entrypoint or registry — not forking the underlying skill content.

## Repository Layout

```
.agents/plugins/marketplace.json     Codex marketplace registry
.claude-plugin/marketplace.json      Claude Code marketplace registry
plugins/                             Plugin sources (one directory per plugin)
AGENTS.md                            Entrypoint for AI coding agents
ARCHITECTURE.md                      How plugins, skills, and registries fit together
README.md                            This file
```

See `ARCHITECTURE.md` for the plugin and skill format conventions.

## Plugins

### `autoreview`

A deterministic pre-commit review gate. A git-commit hook runs a fast, zero-LLM check over the staged change and, for non-trivial / sensitive / hand-resolved-merge changes, blocks the commit and asks the agent to run a multi-perspective review (correctness, security, conventions) before re-committing. Truly trivial changes (docs, small diffs) pass silently; sensitive changes such as dependency manifests, CI, Dockerfiles, migrations, and auth/security paths always get reviewed even when small. After the host installs and trusts/enables the hook, there is no runtime setup beyond `python3`; the gate fails open if it is missing.

The gate supports both ordinary `git commit` in the hook working directory and direct `git -C <worktree> commit` for autonomous agents working from isolated worktrees. Shell `cd` wrappers, nested shell strings, repo/index overrides, and compound staging-plus-commit commands remain unsupported.

| Component | Description |
|---|---|
| `autoreview` skill | Launches bundled and project-local reviewer profiles over staged diff/context, aggregates strict JSON outcomes, and drives a fix-or-dispute loop before re-committing |
| pre-commit hook | A `PreToolUse` hook on `git commit` that runs the deterministic gate (Python, fail-open) and blocks risky commits with a directive to review |

See `plugins/autoreview/README.md` for the plugin contract, schema, validation matrix, and hook trust notes.

Consumer repositories may add custom autoreview reviewers as markdown files under `.agents/autoreview/reviewers/`. These reviewers are additive in v1; they do not override or disable the bundled correctness, security, and conventions reviewers.

## Installing

### Claude Code

Add this repository as a marketplace, then install the plugins you want:

```bash
claude plugin marketplace add Accent-Labs/open-agent-skills
claude plugin install autoreview@open-agent-skills
```

### OpenAI Codex

Codex resolves plugins through `.agents/plugins/marketplace.json`. Point Codex at this repository per its plugin documentation and install the plugins you want.

## Contributing

Contributions are welcome. Before opening a pull request:

1. Read `ARCHITECTURE.md` for the plugin and skill format conventions.
2. Update every marketplace registry and per-plugin manifest when introducing a new plugin.
3. Keep skill content agent-neutral — tool-specific guidance belongs in the entrypoint files (`AGENTS.md`, etc.), not in the shared skill.

## License

MIT. See `LICENSE`.
