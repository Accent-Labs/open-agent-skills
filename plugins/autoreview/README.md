# Autoreview Plugin

`autoreview` is a deterministic pre-commit gate for AI coding agents. It keeps the hook path fast and zero-LLM, then asks the host agent to run a structured multi-reviewer workflow only when the staged change is risky enough to deserve review.

## Components

| Component | Purpose |
|---|---|
| `hooks/hooks.json` | Primary `PreToolUse` hook wiring for shell commands |
| `hooks.json` | Compatibility copy of the hook definition; keep byte-identical with `hooks/hooks.json` |
| `scripts/gate.sh` | POSIX fail-open wrapper that preserves only intentional exit `2` review blocks |
| `scripts/gate.py` | Python entrypoint for the deterministic gate and `mark` subcommand |
| `scripts/autoreview/` | Gate logic, git access, diff parsing, classification, marker, and schema validation |
| `agents/*.md` | Provider-neutral bundled reviewer personas for correctness, security, and conventions |
| `skills/autoreview/SKILL.md` | Host-agent workflow for staged context, reviewer fanout, aggregation, marker writing, and retrying the commit |

## Gate Contract

The hook allows only one plain staged `git commit` in the hook working directory, or one direct `git -C <worktree> commit ...` for agents committing from an explicit worktree path. Environments that prefix shell commands with `rtk` may use `rtk git commit ...` or `rtk git -C <worktree> commit ...`; the gate treats `rtk` as a transparent command proxy and still applies the same commit-shape checks to the wrapped command. It blocks unsupported forms before looking for a marker:

- `-a`, `-am`, `--amend`, `--patch`, `--interactive`, pathspec commits
- multiple commits or compound commands that stage or mutate the index
- shell directory changes such as `cd`, `pushd`, `env -C`, and `env --chdir`
- `--git-dir`, `--work-tree`, `GIT_*` index/repo overrides
- nested shell execution such as `sh -c`, `bash -c`, `zsh -c`, `eval`, command substitution, backticks, and inline function wrappers when a commit is present

The parser is intentionally conservative. It does not emulate shell execution and cannot see aliases or functions that are defined outside the tool input.

## Subagent Worktrees

Subagents working in isolated worktrees should prefer running shell commands with the tool working directory set to that worktree. When that is not available, use `git -C "$WORKTREE"` consistently for every staged-tree operation:

```sh
git -C "$WORKTREE" diff --cached
git -C "$WORKTREE" show :path
python3 "${ROOT}/scripts/gate.py" mark --cwd "$WORKTREE" --payload '<JSON>'
git -C "$WORKTREE" commit -m "subject"
```

Do not wrap the commit in `cd "$WORKTREE" && ...`, `sh -c`, or helper functions. Those forms are still unsupported because the gate does not emulate shell execution.

## Review Contract

Reviewers consume staged diff and staged context by value. They must not read live working-tree files because unstaged edits may differ from the staged tree being committed.

Bundled reviewer personas live in `agents/*.md`. A consumer repository may add project-local reviewers as markdown drop-ins:

```text
<repo-root>/.agents/autoreview/reviewers/<reviewer-id>.md
```

Project-local reviewers are additive in v1. The bundled `correctness`, `security`, and `conventions` reviewers always run first, followed by project-local reviewers sorted by reviewer id. Project-local files cannot override bundled reviewers, disable bundled reviewers, configure ordering, select per-path reviewers, or select models/tools.

Each project-local reviewer must be a regular UTF-8 `.md` file below `.agents/autoreview/reviewers/`, with frontmatter `name` matching the filename stem, a non-empty `description`, a safe lowercase reviewer id, and a non-empty body. Invalid prompt files and duplicate reviewer ids are reported as `NEEDS_CONTEXT` reviewer metadata with zero feedback, so they block marker writing without inflating severity counts.

Use the read-only helper to inspect the effective reviewer set for a repo or worktree:

```sh
python3 plugins/autoreview/scripts/gate.py reviewers --cwd "$PWD"
```

The helper resolves the git worktree root, returns assembled reviewer prompts with the shared JSON response contract appended, and reports prompt-load errors separately.

Every reviewer returns exactly one JSON object:

```json
{
  "reviewer": "correctness",
  "outcome": "APPROVED",
  "summary": "No correctness defects found.",
  "feedback": []
}
```

Reviewer output must be raw JSON only, with no Markdown fences in the actual response. `summary` is required. `line` must be a positive integer for line-specific findings; use `null` only for file-level findings or protocol/context cases.

Allowed outcomes:

| Outcome | Meaning |
|---|---|
| `APPROVED` | No feedback; authorizes marker writing if every reviewer is non-blocking |
| `COMMENTED` | Only low/info non-blocking feedback |
| `CHANGES_REQUESTED` | At least one blocking item; does not authorize marker writing |
| `NEEDS_CONTEXT` | Staged material was insufficient or reviewer JSON was invalid; does not authorize marker writing |

Feedback entries use this shape:

```json
{
  "severity": "high",
  "path": "src/app.py",
  "line": 42,
  "title": "Authorization check is bypassed",
  "impact": "Unauthenticated users can access private data.",
  "evidence": "The staged diff removes the only guard before the data read.",
  "recommendation": "Restore the guard before calling the data loader.",
  "blocking": true
}
```

The aggregator injects `reviewer` into feedback items mechanically. Reviewer protocol failures, invalid JSON, and context gaps are represented in the aggregate `reviewers` metadata instead of as synthetic high-severity feedback, so severity counts cover real feedback only.

## Marker Contract

`scripts/gate.py mark --payload '<JSON>'` writes a marker only for final aggregate outcomes that authorize a commit:

- `APPROVED`
- `COMMENTED` with only non-blocking low/info feedback

The marker validator rejects malformed JSON, old verdict names, `CHANGES_REQUESTED`, `NEEDS_CONTEXT`, missing fields, mismatched counts, and blocking feedback. Markers are keyed to the staged tree and consumed once.

Authorizing marker payloads may include reviewer metadata such as `summary`, `status`, and `error`, but only `reviewer` and an authorizing `outcome` are required for each reviewer entry.

When reviewing an explicit `git -C <worktree> commit` target from another directory, pass `--cwd <worktree>` to write the marker into that target repo's git dir.

## Validation

Run the deterministic suite:

```sh
sh plugins/autoreview/scripts/run_tests.sh
```

The command runs unit tests plus real temporary-repository eval fixtures.

Recommended live checks before release:

| Surface | Check |
|---|---|
| Hook load | Install the plugin, trust/enable the hook if the host requires it, and run a risky staged `git commit` through the host agent CLI |
| Block contract | Confirm hook exit `2` blocks the commit and surfaces the autoreview directive |
| Fail-open | Simulate missing Python or malformed hook input and confirm commit is not blocked |
| Marker round trip | Run review, write an authorizing marker, confirm one plain commit is allowed and marker is consumed |
| Worktree target | Run a staged `git -C <worktree> commit` from a different hook cwd and confirm the gate reads and writes markers in the target worktree |
| Reviewer workflow | Confirm the host agent can launch the three profile workers and collect strict JSON |

## Runtime

The deterministic gate uses Python 3 standard library only. It prefers system `python3` through `gate.sh` and fails open if no Python runtime is available.

Host notes:

- Claude Code loads `hooks/hooks.json` through the plugin manifest and passes `CLAUDE_PLUGIN_ROOT`.
- OpenAI Codex loads `hooks/hooks.json` from `.codex-plugin/plugin.json`; Codex installations must have the stable `hooks` feature enabled and must trust the plugin hook before it runs. Codex passes both `PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT`.
