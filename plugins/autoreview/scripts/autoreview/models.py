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


def safe_text(s: str) -> str:
    # Strip control/newline/non-printable chars so repo-controlled text (filenames, error
    # messages) cannot inject lines into agent-facing output.
    return "".join(c if (c.isprintable() and c not in "\r\n") else "?" for c in s)


class CommandAnalysis(NamedTuple):
    """Parsed shell command shape for the commit gate."""

    commits: List[List[str]]
    has_mutator: bool
    unsafe: bool
    has_commit: bool
    target_cwd: Optional[str] = None


class Classification(NamedTuple):
    action: str               # SKIP | REVIEW
    reason: str = ""


class Decision(NamedTuple):
    action: str               # ALLOW | BLOCK
    message: str = ""


class ReviewerProfile(NamedTuple):
    reviewer: str
    source: str               # bundled | project_local
    path: str
    description: str
    persona_markdown: str

    def to_dict(self, prompt: Optional[str] = None) -> dict:
        data = {
            "reviewer": self.reviewer,
            "source": self.source,
            "path": self.path,
            "description": self.description,
        }
        if prompt is not None:
            data["prompt"] = prompt
        return data


class ProfileLoadError(NamedTuple):
    reviewer: str
    source: str               # bundled | project_local
    path: str
    kind: str
    message: str

    def to_reviewer_result(self) -> dict:
        from . import schema
        return schema.needs_context_result(self.reviewer, self.message, self.kind)

    def to_dict(self) -> dict:
        return {
            "reviewer": self.reviewer,
            "source": self.source,
            "path": self.path,
            "kind": self.kind,
            "message": self.message,
            "review_result": self.to_reviewer_result(),
        }
