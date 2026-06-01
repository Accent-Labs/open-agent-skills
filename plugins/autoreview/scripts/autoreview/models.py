from __future__ import annotations
from typing import NamedTuple, Optional

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


class Classification(NamedTuple):
    action: str               # SKIP | REVIEW
    reason: str = ""


class Decision(NamedTuple):
    action: str               # ALLOW | BLOCK
    message: str = ""
