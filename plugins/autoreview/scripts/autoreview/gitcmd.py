from __future__ import annotations
import os
import re
import subprocess
from typing import List, Optional

_CONFLICTS_RE = re.compile(r"(?m)^#?\s*Conflicts:")  # MERGE_MSG writes "# Conflicts:" (commented)


class Git:
    """All git I/O lives here so it is uniformly injectable/mockable in tests.

    Output is decoded utf-8/surrogateescape because paths may not be valid UTF-8.
    """

    def __init__(self, cwd: str):
        self.cwd = cwd

    def _decode(self, b: bytes) -> str:
        return b.decode("utf-8", "surrogateescape")

    def run(self, args: List[str]) -> str:
        p = subprocess.run(["git", *args], cwd=self.cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode != 0:
            raise subprocess.CalledProcessError(p.returncode, ["git", *args], p.stdout, p.stderr)
        return self._decode(p.stdout)

    def run_ok(self, args: List[str]) -> Optional[str]:
        """For commands whose nonzero exit is expected/normal (e.g. rev-parse --quiet)."""
        p = subprocess.run(["git", *args], cwd=self.cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return self._decode(p.stdout) if p.returncode == 0 else None

    def git_path(self, name: str) -> str:
        # `rev-parse --git-path` returns a path relative to the repo; resolve against
        # self.cwd so callers can use it regardless of the process working directory.
        p = self.run(["rev-parse", "--git-path", name]).strip()
        return p if os.path.isabs(p) else os.path.join(self.cwd, p)

    def detect_state(self) -> str:
        def has(name: str) -> bool:
            # Only an expected git failure (e.g. not yet a repo) is tolerated here; any other
            # exception propagates to the CLI fail-open boundary (which warns) rather than being
            # silently masked as state="normal".
            try:
                return os.path.exists(self.git_path(name))
            except subprocess.CalledProcessError:
                return False
        if has("MERGE_HEAD"):
            return "merge"
        if has("CHERRY_PICK_HEAD"):
            return "cherry-pick"
        if has("REVERT_HEAD"):
            return "revert"
        if has("rebase-merge") or has("rebase-apply"):
            return "rebase"
        return "normal"

    def write_tree(self) -> str:
        return self.run(["write-tree"]).strip()

    def compute_identity(self, state: str) -> str:
        tree = self.write_tree()
        if state != "merge":
            return tree
        head = self.run(["rev-parse", "HEAD"]).strip()
        parents = [s.strip() for s in self.run(["rev-parse", "MERGE_HEAD"]).strip().split("\n") if s.strip()]
        return ":".join([tree, head, *parents])

    def merge_needs_review(self) -> bool:
        auto = self.run_ok(["rev-parse", "--verify", "--quiet", "AUTO_MERGE"])
        auto = auto.strip() if auto else ""
        if auto:
            return self.write_tree() != self.run(["rev-parse", auto + "^{tree}"]).strip()
        try:
            with open(self.git_path("MERGE_MSG"), encoding="utf-8", errors="surrogateescape") as fh:
                if _CONFLICTS_RE.search(fh.read()):
                    return True
        except OSError:
            pass
        return False

    def staged_numstat(self) -> str:
        return self.run(["diff", "--cached", "-z", "--numstat", "-M"])
