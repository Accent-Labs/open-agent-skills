# Coding Agent Instructions

This repository hosts a multi-agent skills library. The plugins and skills here are designed to be loaded by AI coding tools — Claude Code, OpenAI Codex, and other compatible agents — through tool-specific registries that all point at the same underlying `plugins/` tree.

If you are an AI coding agent reading this file, treat the Markdown files as the source of truth and apply the conventions below before editing.

## Project Overview

- `plugins/<plugin-name>/skills/<skill-name>/SKILL.md` is the canonical skill document.
- `.claude-plugin/marketplace.json` is the Claude Code registry.
- `.agents/plugins/marketplace.json` is the OpenAI Codex registry.
- `plugins/<plugin-name>/.claude-plugin/plugin.json` is the per-plugin Claude Code manifest.
- `plugins/<plugin-name>/.codex-plugin/plugin.json` is the per-plugin Codex manifest.

Every registry and manifest should list the same plugins in the same order unless a tool-specific compatibility issue requires an exception.

## Editing Rules

When adding or modifying a plugin:

1. Update both `.claude-plugin/marketplace.json` and `.agents/plugins/marketplace.json`.
2. Add or update `plugins/<plugin-name>/.claude-plugin/plugin.json` (Claude Code per-plugin manifest).
3. Add or update `plugins/<plugin-name>/.codex-plugin/plugin.json` with `skills` set to `./skills/`.
4. Add the plugin and its skills to the relevant tables in `README.md` and `ARCHITECTURE.md`.

When adding or modifying a skill:

1. Place the skill at `plugins/<plugin>/skills/<skill-name>/SKILL.md`.
2. The frontmatter `name` must match the containing directory name exactly.
3. The frontmatter `description` is the primary routing signal — enumerate trigger conditions, covered topics, and common user questions that should activate the skill.

See `ARCHITECTURE.md` for the full skill document format and content conventions.

## Agent-Neutrality

Keep skill content agent-neutral. If a rule depends on a specific agent's discovery mechanism, document that dependency in `ARCHITECTURE.md` or the relevant entrypoint file rather than in the shared skill body.

## Adding Support for a New Agent

1. Add a new entrypoint or registry file specific to that agent.
2. Document the discovery behavior in `ARCHITECTURE.md`.
3. Do not fork shared skill content unless the target agent requires a different syntax.
