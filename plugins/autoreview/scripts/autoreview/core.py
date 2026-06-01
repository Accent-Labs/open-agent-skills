from __future__ import annotations
import os
from typing import List, Optional
from . import diffparse, markers
from .classify import classify
from .gitcmd import Git
from .models import Decision, FileDelta, ALLOW, BLOCK, SKIP

# Absolute install dir of this plugin (…/plugins/autoreview), derived from this file's location so
# the skill can locate scripts/ even if $CLAUDE_PLUGIN_ROOT/$PLUGIN_ROOT are unset in its context.
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

UNSUPPORTED_DIRECTIVE = (
    "Autoreview supports plain staged commits only. Stage your changes explicitly (`git add ...`) "
    "and run a plain `git commit`; do not use -a/-am/--amend/--patch/--interactive/<pathspec>. "
    "(No autoreview marker is written for this command form.)"
)

COMPOUND_DIRECTIVE = (
    "Autoreview can only verify a single plain `git commit` of the staged tree in the current "
    "directory. Run nothing in the same command that changes what gets committed — no staging "
    "(`git add` ...), no chained/multiple commits, no `cd`/`git -C`/`--git-dir`/`--work-tree`, no "
    "GIT_* env overrides, and no `env -S`/`time`/other wrappers. Stage in this repo, then run a plain "
    "`git commit` on its own."
)


def _safe_path(p: str) -> str:
    # Strip control/newline/non-printable chars so a crafted filename can't inject text into the
    # agent-facing directive.
    return "".join(c if (c.isprintable() and c not in "\r\n") else "?" for c in p)


def review_directive(reason: str, files: Optional[List[FileDelta]]) -> str:
    if files:
        names = ", ".join(_safe_path(f.path) for f in files[:20])
        stats = f"Change: {len(files)} files{(' - ' + names) if names else ''}. "
    else:
        stats = ""
    return (f"Autoreview required ({reason}). Invoke the `autoreview` skill now: review the staged "
            f"change with the bundled reviewer profiles, address or dispute findings, then re-commit. "
            f"{stats}(autoreview plugin dir: {PLUGIN_ROOT} — use this as ROOT for scripts/ if "
            f"$CLAUDE_PLUGIN_ROOT/$PLUGIN_ROOT are unset.)").strip()


def decide_gate(inp: dict, git_factory=Git) -> Decision:
    """Pure orchestration. Raises on internal error — cli.main() is the fail-open boundary."""
    cwd = inp.get("cwd") or os.getcwd()
    command = (inp.get("tool_input") or {}).get("command", "") or ""

    commits, has_mutator, unsafe, has_commit = diffparse.analyze_command(command)
    if not has_commit:
        return Decision(ALLOW)  # no git commit anywhere in this command

    git = git_factory(cwd)
    state = git.detect_state()
    if state in ("cherry-pick", "revert", "rebase"):
        return Decision(ALLOW)  # never wedge an in-flight operation (it runs git commit internally)

    # Command-only decisions happen BEFORE the marker lookup, so a marker written for the staged
    # tree can never authorize a command whose effective commit content differs from that tree
    # (-a/-am, --amend, pathspec, interactive, staging, multiple commits, or a form that changes the
    # cwd/repo/index — cd/git -C/GIT_* env/env -S/time/unknown wrappers).
    flags_list = [diffparse.parse_commit_flags(a) for a in commits]
    # Honor explicit --no-verify only for a single cleanly-parsed plain commit in the hook cwd.
    if len(commits) == 1 and not unsafe and not has_mutator and flags_list[0].no_verify:
        return Decision(ALLOW)  # explicit bypass (cli logs the warning)
    if any(f.all or f.amend or f.pathspec or f.interactive for f in flags_list):
        return Decision(BLOCK, UNSUPPORTED_DIRECTIVE)
    if unsafe or has_mutator or len(commits) != 1:
        return Decision(BLOCK, COMPOUND_DIRECTIVE)

    merge_forces = False
    if state == "merge":
        try:
            merge_forces = git.merge_needs_review()
        except Exception:
            merge_forces = True  # intentional degrade-to-safe: a merge we cannot assess gets reviewed

    identity = git.compute_identity(state)
    mdir = markers.marker_dir(git)
    markers.gc(mdir)
    mpath = markers.marker_path(mdir, identity)
    if markers.read(mpath) == "valid":
        markers.consume(mpath)
        return Decision(ALLOW)

    if state == "merge" and merge_forces:
        return Decision(BLOCK, review_directive("merge conflict resolution", None))

    files = diffparse.parse_numstat_z(git.staged_numstat())
    result = classify(files)
    if result.action == SKIP:
        return Decision(ALLOW)
    return Decision(BLOCK, review_directive(result.reason, files))
