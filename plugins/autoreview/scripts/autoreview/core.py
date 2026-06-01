from __future__ import annotations
import os
from typing import List, Optional
from . import diffparse, markers
from .classify import classify
from .gitcmd import Git
from .models import Decision, FileDelta, ALLOW, BLOCK, SKIP

UNSUPPORTED_DIRECTIVE = (
    "Autoreview supports plain staged commits only. Stage your changes explicitly (`git add ...`) "
    "and run a plain `git commit`; do not use -a/-am/--amend/<pathspec>. "
    "(No autoreview marker is written for this command form.)"
)


def review_directive(reason: str, files: Optional[List[FileDelta]]) -> str:
    if files:
        names = ", ".join(f.path for f in files[:20])
        stats = f"Change: {len(files)} files{(' - ' + names) if names else ''}. "
    else:
        stats = ""
    return (f"Autoreview required ({reason}). Invoke the `autoreview` skill now: review the staged "
            f"change with the configured reviewers, address or dispute findings, then re-commit. "
            f"{stats}").strip()


def decide_gate(inp: dict, git_factory=Git) -> Decision:
    """Pure orchestration. Raises on internal error — cli.main() is the fail-open boundary."""
    cwd = inp.get("cwd") or os.getcwd()
    command = (inp.get("tool_input") or {}).get("command", "") or ""

    commit_args = diffparse.find_git_commit(command)
    if commit_args is None:
        return Decision(ALLOW)
    flags = diffparse.parse_commit_flags(commit_args)
    git = git_factory(cwd)

    state = git.detect_state()
    if state in ("cherry-pick", "revert", "rebase"):
        return Decision(ALLOW)

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

    if flags.no_verify:
        return Decision(ALLOW)  # bypass (cli logs the warning)
    if flags.all or flags.amend or flags.pathspec:
        return Decision(BLOCK, UNSUPPORTED_DIRECTIVE)
    if state == "merge" and merge_forces:
        return Decision(BLOCK, review_directive("merge conflict resolution", None))

    files = diffparse.parse_numstat_z(git.staged_numstat())
    result = classify(files)
    if result.action == SKIP:
        return Decision(ALLOW)
    return Decision(BLOCK, review_directive(result.reason, files))
