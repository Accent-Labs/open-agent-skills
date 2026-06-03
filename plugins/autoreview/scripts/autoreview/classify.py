from __future__ import annotations

import re
from typing import Iterable, List, Pattern, Tuple

from .models import Classification, FileDelta, REVIEW, SKIP

_SENSITIVE = [re.compile(p) for p in (
    r"(^|/)\.github/workflows/", r"(^|/)\.gitlab-ci\.yml$", r"(^|/)\.circleci/",
    r"(^|/)Dockerfile($|\.)", r"(^|/)docker-compose\.ya?ml$",
    r"\.config\.[^/]+$", r"(^|/)(migrations?|db/migrate)/", r"(^|/)(auth|security)/",
)]
_DEP = [re.compile(p) for p in (
    r"(^|/)package\.json$", r"(^|/)package-lock\.json$", r"(^|/)yarn\.lock$", r"(^|/)pnpm-lock\.yaml$",
    r"(^|/)Gemfile(\.lock)?$", r"(^|/)requirements[^/]*\.txt$", r"(^|/)poetry\.lock$", r"(^|/)pyproject\.toml$",
    r"(^|/)go\.(mod|sum)$", r"(^|/)Cargo\.(toml|lock)$", r"(^|/)composer\.(json|lock)$",
)]
_GENERATED = [re.compile(p) for p in (
    r"(^|/)vendor/", r"(^|/)node_modules/", r"(^|/)dist/", r"(^|/)build/",
    r"\.min\.(js|css)$", r"\.generated\.[^/]+$", r"(^|/)gen/",
)]
_DOC = [re.compile(p) for p in (r"\.md$", r"\.mdx$", r"\.txt$", r"\.rst$", r"(^|/)docs?/")]


def _matches_any(patterns: Iterable[Pattern[str]], path: str) -> bool:
    return any(rx.search(path) for rx in patterns)


def _paths_for(delta: FileDelta) -> Tuple[str, ...]:
    if delta.old_path:
        return (delta.path, delta.old_path)
    return (delta.path,)


def _is_sensitive(delta: FileDelta) -> bool:
    return any(_matches_any(_SENSITIVE, path) or _matches_any(_DEP, path) for path in _paths_for(delta))


def _is_generated(delta: FileDelta) -> bool:
    return _matches_any(_GENERATED, delta.path)


def _is_doc(delta: FileDelta) -> bool:
    return _matches_any(_DOC, delta.path)


def classify(files: List[FileDelta], threshold: int = 20) -> Classification:
    if not files:
        return Classification(SKIP, "empty diff")
    if any(_is_sensitive(f) for f in files):
        return Classification(REVIEW, "sensitive path or dependency manifest")
    if any(f.binary and not _is_generated(f) for f in files):
        return Classification(REVIEW, "binary/unknown file")
    if all(_is_generated(f) for f in files):
        return Classification(SKIP, "generated/vendored only")
    if all(_is_doc(f) or _is_generated(f) for f in files):
        return Classification(SKIP, "docs only")
    total = sum(0 if f.binary else f.added + f.deleted for f in files)
    if total < threshold:
        return Classification(SKIP, f"small change ({total} lines)")
    return Classification(REVIEW, f"non-trivial change ({total} lines)")
