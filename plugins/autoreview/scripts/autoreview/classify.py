from __future__ import annotations
import re
from typing import List
from .models import FileDelta, Classification, SKIP, REVIEW

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


def _any(patterns, path: str) -> bool:
    return any(rx.search(path) for rx in patterns)


def _both_paths(f: FileDelta):
    return (f.path, f.old_path) if f.old_path else (f.path,)


def classify(files: List[FileDelta], threshold: int = 20) -> Classification:
    if not files:
        return Classification(SKIP, "empty diff")
    # Sensitive/dependency checks consider BOTH paths so a rename away from (or to) a
    # sensitive path is still reviewed.
    sensitive = lambda f: any(_any(_SENSITIVE, p) or _any(_DEP, p) for p in _both_paths(f))  # noqa: E731
    generated = lambda f: _any(_GENERATED, f.path)  # noqa: E731
    doc = lambda f: _any(_DOC, f.path)  # noqa: E731
    if any(sensitive(f) for f in files):
        return Classification(REVIEW, "sensitive path or dependency manifest")
    if any(f.binary and not generated(f) for f in files):
        return Classification(REVIEW, "binary/unknown file")
    if all(generated(f) for f in files):
        return Classification(SKIP, "generated/vendored only")
    if all(doc(f) or generated(f) for f in files):
        return Classification(SKIP, "docs only")
    total = sum(0 if f.binary else f.added + f.deleted for f in files)
    if total < threshold:
        return Classification(SKIP, f"small change ({total} lines)")
    return Classification(REVIEW, f"non-trivial change ({total} lines)")
