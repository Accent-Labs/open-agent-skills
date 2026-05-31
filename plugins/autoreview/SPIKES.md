# Autoreview — Phase 0 Validation Spike Findings

Environment: macOS (Darwin 25.x), Apple git 2.50.1. Recorded during Phase 0.

## Runtime availability (BLOCKING finding) — decided: Python 3

`node` is **not installed** on this machine — no binary on PATH, none in `/opt/homebrew/bin`,
`/usr/local/bin`, `/usr/bin`, and no nvm/volta/fnm. The `claude` and `codex` CLIs are standalone
binaries that do not expose a node.

Interpreters that ARE present:

| Runtime | Path | Version |
|---|---|---|
| python3 | /usr/bin/python3 | 3.9.6 (macOS CLT system Python) |
| jq | /usr/bin/jq | 1.7.1 |
| perl | /usr/bin/perl | system |
| ruby | ~/.rbenv/shims/ruby | 2.6.10 (rbenv) |
| awk / sed / bash | /usr/bin, /bin/sh = bash 3.2.57 | — |
| **node** | — | **MISSING** |

**Decision:** the gate stack is implemented in **Python 3 (standard library only)** — `json`,
`subprocess`, `re`, `hashlib`, `pathlib`, `tempfile`, `unittest`. `/usr/bin/python3` ships with the
Apple Command Line Tools (present here, since Apple git is installed) and is ubiquitous on Linux.
A Node implementation would fail-open on every commit on this machine and silently never review.
`gate.sh` invokes `python3` (fail-open if absent). Architecture is otherwise unchanged.

## Tool detection env (0.3) — partial

- **Claude Code:** `CLAUDECODE=1` confirmed in-session. ✅
- **Codex:** `CODEX_THREAD_ID` / `CODEX_SHELL` / `CODEX_CI` to be confirmed inside a real Codex
  session (not yet run). The registry detects Codex via any of these.
- `CLAUDE_PLUGIN_ROOT` / `PLUGIN_ROOT` are empty in the plain interactive session (expected — they
  are populated by the plugin/hook runtime, not a normal shell). Confirm in the hook + skill contexts.

## Merge signals (0.4) — validated, with a regex fix

During a conflicted `git merge` (Apple git 2.50.1, ORT default):
- `MERGE_HEAD`, `AUTO_MERGE`, and `MERGE_MSG` all exist.
- `AUTO_MERGE` is resolvable (`git rev-parse --verify --quiet AUTO_MERGE`). ✅
- After a hand-resolution staged with `git add`, the index tree (`git write-tree`) **differs** from
  the `AUTO_MERGE` tree → the primary "hand-resolution → REVIEW" heuristic works. ✅
- **Fix:** the `MERGE_MSG` conflicts section is written as `# Conflicts:` (commented), NOT
  `Conflicts:`. The fallback regex must be `^#?\s*Conflicts:` (multiline), not `^Conflicts:`.
  The AUTO_MERGE tree comparison is the reliable primary path; MERGE_MSG is the fallback when
  AUTO_MERGE is absent (older git).

## codex CLI surface (for Codex-side spikes)

`codex` subcommands include `exec` (non-interactive; prompt as arg or stdin), `review`, `plugin`,
`doctor`, `sandbox`. `codex exec` supports `-c key=value` config overrides and `-m model`.
Useful for driving the remaining Codex hook/detection/spawn spikes.

## Still pending (require live CC/Codex sessions)

- 0.1 hook discovery path (root `hooks.json` vs `hooks/hooks.json`) per tool.
- 0.2 stdin shape + exit-2 block + stderr-feedback contract per tool.
- 0.5 tool detection + plugin-root from the SKILL (main-agent) context.
- 0.6 spawn paths — Claude Code native `agents/<id>.md` by name; Codex/generic inline worker.
- Codex detection env confirmation (CODEX_THREAD_ID present in a Codex session).
