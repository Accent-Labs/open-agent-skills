from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Tuple

from . import schema
from .models import ProfileLoadError, ReviewerProfile


PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUNDLED_REVIEWERS_DIR = os.path.join(PLUGIN_ROOT, "agents")
BUNDLED_REVIEWER_ORDER = ("correctness", "security", "conventions")
LOCAL_REVIEWERS_REL = os.path.join(".agents", "autoreview", "reviewers")
MAX_PROFILE_BYTES = 64 * 1024
REVIEWER_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


class ProfileParseError(ValueError):
    def __init__(self, reviewer: str, kind: str, message: str):
        super().__init__(message)
        self.reviewer = reviewer
        self.kind = kind
        self.message = message


def _parse_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    if not text.startswith("---\n"):
        raise ProfileParseError("", "invalid_prompt", "reviewer prompt is missing frontmatter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ProfileParseError("", "invalid_prompt", "reviewer prompt frontmatter is not closed")
    raw = text[4:end]
    body = text[end + 5:].strip()
    data: Dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data, body


def _safe_reviewer_from_path(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def _validate_file(path: str) -> None:
    if os.path.islink(path):
        raise ProfileParseError(_safe_reviewer_from_path(path), "invalid_prompt",
                                "reviewer prompt must be a regular file, not a symlink")
    if not os.path.isfile(path):
        raise ProfileParseError(_safe_reviewer_from_path(path), "invalid_prompt",
                                "reviewer prompt must be a regular markdown file")
    if os.path.getsize(path) > MAX_PROFILE_BYTES:
        raise ProfileParseError(_safe_reviewer_from_path(path), "invalid_prompt",
                                "reviewer prompt exceeds %d bytes" % MAX_PROFILE_BYTES)


def load_bundled_profile(path: str) -> ReviewerProfile:
    return _load_profile_file(path, "bundled")


def _load_profile_file(path: str, source: str) -> ReviewerProfile:
    _validate_file(path)
    stem = _safe_reviewer_from_path(path)
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except UnicodeDecodeError as exc:
        raise ProfileParseError(stem, "invalid_prompt", "reviewer prompt must be valid UTF-8") from exc

    try:
        frontmatter, body = _parse_frontmatter(text)
    except ProfileParseError as exc:
        reviewer = exc.reviewer or stem
        raise ProfileParseError(reviewer, exc.kind, exc.message) from exc

    reviewer = frontmatter.get("name", "").strip()
    description = frontmatter.get("description", "").strip()
    if not REVIEWER_ID_RE.match(stem):
        raise ProfileParseError(stem, "invalid_prompt",
                                "reviewer filename must match %s" % REVIEWER_ID_RE.pattern)
    if reviewer != stem:
        raise ProfileParseError(stem, "invalid_prompt",
                                "frontmatter name must match filename stem %s" % stem)
    if not description:
        raise ProfileParseError(stem, "invalid_prompt", "frontmatter description must be non-empty")
    if not body:
        raise ProfileParseError(stem, "invalid_prompt", "reviewer prompt body must be non-empty")
    return ReviewerProfile(stem, source, path, description, body)


def _error_from_parse(path: str, source: str, exc: ProfileParseError) -> ProfileLoadError:
    reviewer = exc.reviewer or _safe_reviewer_from_path(path)
    return ProfileLoadError(reviewer, source, path, exc.kind, exc.message)


def _bundled_paths(bundled_dir: str) -> List[str]:
    return [os.path.join(bundled_dir, reviewer + ".md") for reviewer in BUNDLED_REVIEWER_ORDER]


def _discover_local_profiles(
    repo_root: str,
    seen: Dict[str, str],
) -> Tuple[List[ReviewerProfile], List[ProfileLoadError]]:
    profiles: List[ReviewerProfile] = []
    errors: List[ProfileLoadError] = []
    local_dir = os.path.join(repo_root, LOCAL_REVIEWERS_REL)
    if not os.path.isdir(local_dir):
        return profiles, errors

    for filename in sorted(os.listdir(local_dir)):
        if not filename.endswith(".md"):
            continue
        path = os.path.join(local_dir, filename)
        try:
            profile = _load_profile_file(path, "project_local")
        except ProfileParseError as exc:
            errors.append(_error_from_parse(path, "project_local", exc))
            continue
        except OSError as exc:
            # An unreadable profile must surface as a load error (which blocks marking), never be
            # silently skipped: skipping would let a required reviewer vanish from the gate.
            errors.append(ProfileLoadError(
                _safe_reviewer_from_path(path), "project_local", path,
                "invalid_prompt", "reviewer prompt is unreadable: %s" % exc,
            ))
            continue
        if profile.reviewer in seen:
            errors.append(ProfileLoadError(
                profile.reviewer,
                "project_local",
                path,
                "duplicate_reviewer",
                "reviewer %s is already defined by %s" % (profile.reviewer, seen[profile.reviewer]),
            ))
            continue
        profiles.append(profile)
        seen[profile.reviewer] = profile.path
    return profiles, errors


def discover_reviewer_profiles(
    repo_root: str,
    bundled_dir: str = BUNDLED_REVIEWERS_DIR,
) -> Tuple[List[ReviewerProfile], List[ProfileLoadError]]:
    profiles: List[ReviewerProfile] = []
    errors: List[ProfileLoadError] = []
    seen: Dict[str, str] = {}

    for path in _bundled_paths(bundled_dir):
        try:
            profile = _load_profile_file(path, "bundled")
        except ProfileParseError as exc:
            errors.append(_error_from_parse(path, "bundled", exc))
            continue
        profiles.append(profile)
        seen[profile.reviewer] = profile.path

    local_profiles, local_errors = _discover_local_profiles(repo_root, seen)
    return profiles + local_profiles, errors + local_errors


def required_reviewer_ids(repo_root: str) -> Tuple[List[str], List[ProfileLoadError]]:
    """Reviewer ids an authorizing marker must cover for this repo: the bundled set plus every
    project-local profile that loads. Project-local load errors are returned so callers can
    fail closed on them; bundled ids are constant and never depend on file reads."""
    seen = {r: os.path.join(BUNDLED_REVIEWERS_DIR, r + ".md") for r in BUNDLED_REVIEWER_ORDER}
    local_profiles, errors = _discover_local_profiles(repo_root, seen)
    return list(BUNDLED_REVIEWER_ORDER) + [p.reviewer for p in local_profiles], errors


def reviewer_response_contract_markdown(reviewer: str) -> str:
    approved = {
        "reviewer": reviewer,
        "outcome": "APPROVED",
        "summary": "No issues found.",
        "feedback": [],
    }
    changes_requested = {
        "reviewer": reviewer,
        "outcome": "CHANGES_REQUESTED",
        "summary": "A staged change introduces a concrete issue.",
        "feedback": [
            {
                "severity": "high",
                "path": "src/app.py",
                "line": 42,
                "title": "Concrete issue title",
                "impact": "Explain the user-visible or system impact.",
                "evidence": "Cite the staged diff or staged context proving the issue.",
                "recommendation": "Describe the minimal fix.",
                "blocking": True,
            }
        ],
    }
    outcomes = ", ".join(schema.OUTCOMES)
    severities = ", ".join(schema.SEVERITIES)
    return """## Response Contract

Return raw JSON only: exactly one JSON object, no Markdown fences, no prose, and no placeholder enum strings. The `reviewer` field must be "%s".

Allowed outcomes: %s.
Allowed severities: %s.

Use `APPROVED` only with empty `feedback`. Use `COMMENTED` only for non-blocking low/info observations. Use `CHANGES_REQUESTED` only when at least one feedback item is blocking. Use `NEEDS_CONTEXT` when the provided staged material is insufficient.

`summary` is required. Use `line: null` only for file-level findings or `NEEDS_CONTEXT`; real line-specific findings must use a positive integer.

Approved example:

```json
%s
```

Changes-requested example:

```json
%s
```
""" % (
        reviewer,
        outcomes,
        severities,
        json.dumps(approved, indent=2),
        json.dumps(changes_requested, indent=2),
    )


def assemble_reviewer_prompt(profile: ReviewerProfile) -> str:
    return "%s\n\n%s" % (
        profile.persona_markdown.strip(),
        reviewer_response_contract_markdown(profile.reviewer).strip(),
    )


def reviewers_payload(repo_root: str) -> dict:
    profiles, errors = discover_reviewer_profiles(repo_root)
    return {
        "repo_root": repo_root,
        "local_reviewers_dir": os.path.join(repo_root, LOCAL_REVIEWERS_REL),
        "reviewers": [profile.to_dict(prompt=assemble_reviewer_prompt(profile)) for profile in profiles],
        "errors": [error.to_dict() for error in errors],
    }
