# Changelog

## 0.2.0

Project-local reviewer profiles are now deterministically enforced, not just discovered.

- The gate's block directive enumerates the full required reviewer set — the bundled
  `correctness`, `security`, and `conventions` reviewers plus every project-local profile
  discovered under `<repo-root>/.agents/autoreview/reviewers/*.md` — and names invalid
  project-local profiles that must be fixed before committing.
- `gate.py mark` rejects payloads whose `reviewers` array does not cover every required
  reviewer for the target repo, with an error naming the missing reviewers, and rejects all
  payloads while any project-local profile fails to load (malformed, unreadable, oversized,
  symlinked, or duplicating a bundled id).
- The gate re-validates reviewer coverage before honoring a marker, so a marker written
  before a project-local reviewer appeared falls back to a fresh review instead of
  authorizing the commit. The marker payload version stays `2`: the payload shape is
  unchanged, and consume-time coverage validation retires incomplete markers naturally.
- New `gate.py check --cwd <repo>` subcommand reports staged-tree identity, marker status
  (`none` / `valid` / `invalid` / `insufficient`), the required reviewer set, and invalid
  project-local profiles — without consuming the one-shot marker. SKILL.md's validation
  section now uses it and warns that piping hook input into `gate.py` consumes markers.
- SKILL.md and README document the project-local convention path, the additive collision
  rule, the trust model for repo-controlled profile content, and the enforcement semantics.

## 0.1.0

Initial release: deterministic pre-commit gate, bundled correctness/security/conventions
reviewer profiles, staged-tree-keyed one-shot markers, and the autoreview skill workflow.
