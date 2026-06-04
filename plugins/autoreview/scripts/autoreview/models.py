from __future__ import annotations

from typing import List, NamedTuple, Optional

# action vocabularies
ALLOW, BLOCK = "ALLOW", "BLOCK"
SKIP, REVIEW = "SKIP", "REVIEW"


class FileDelta(NamedTuple):
    path: str
    added: int
    deleted: int
    binary: bool
    status: str               # 'M' | 'R' | ...
    old_path: Optional[str] = None


class Flags(NamedTuple):
    all: bool = False
    amend: bool = False
    no_verify: bool = False
    pathspec: bool = False
    interactive: bool = False   # -p / --patch / --interactive (commits selected non-staged hunks)


class CommandAnalysis:
    """Parsed shell command shape for the commit gate.

    Iteration intentionally yields the original four fields so older call sites that unpack
    `analyze_command()` still work while newer code can read `target_cwd`.
    """

    __slots__ = ("commits", "has_mutator", "unsafe", "has_commit", "target_cwd")

    def __init__(
        self,
        commits: List[List[str]],
        has_mutator: bool,
        unsafe: bool,
        has_commit: bool,
        target_cwd: Optional[str] = None,
    ):
        self.commits = commits
        self.has_mutator = has_mutator
        self.unsafe = unsafe
        self.has_commit = has_commit
        self.target_cwd = target_cwd

    def _legacy_tuple(self):
        return (self.commits, self.has_mutator, self.unsafe, self.has_commit)

    def __iter__(self):
        return iter(self._legacy_tuple())

    def __len__(self):
        return 4

    def __getitem__(self, index):
        return self._legacy_tuple()[index]

    def __eq__(self, other):
        if isinstance(other, CommandAnalysis):
            return (
                self.commits == other.commits
                and self.has_mutator == other.has_mutator
                and self.unsafe == other.unsafe
                and self.has_commit == other.has_commit
                and self.target_cwd == other.target_cwd
            )
        if isinstance(other, tuple):
            return self._legacy_tuple() == other
        return NotImplemented

    def __repr__(self):
        base = (
            f"CommandAnalysis(commits={self.commits!r}, has_mutator={self.has_mutator!r}, "
            f"unsafe={self.unsafe!r}, has_commit={self.has_commit!r}"
        )
        if self.target_cwd is not None:
            base += f", target_cwd={self.target_cwd!r}"
        return base + ")"


class Classification(NamedTuple):
    action: str               # SKIP | REVIEW
    reason: str = ""


class Decision(NamedTuple):
    action: str               # ALLOW | BLOCK
    message: str = ""
