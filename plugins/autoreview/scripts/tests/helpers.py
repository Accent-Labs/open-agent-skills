"""Shared fixtures for CLI/core tests: real temp git repos, marker payloads, reviewer profiles."""
from __future__ import annotations

import os
import subprocess
import tempfile

BUNDLED = ("correctness", "security", "conventions")


def run(d, *args):
    return subprocess.run(["git", *args], cwd=d, capture_output=True, text=True, check=True)


def new_repo(prefix="ar-test-"):
    d = tempfile.mkdtemp(prefix=prefix)
    run(d, "init", "-q", "-b", "main")
    run(d, "config", "user.email", "t@t")
    run(d, "config", "user.name", "t")
    run(d, "commit", "--allow-empty", "-q", "-m", "root")
    return d


def stage_nontrivial(d, rel="src.py", lines=40):
    path = os.path.join(d, rel)
    os.makedirs(os.path.dirname(path) or d, exist_ok=True)
    with open(path, "w") as fh:
        fh.write("x\n" * lines)
    run(d, "add", rel)


def approved_marker(*reviewers):
    ids = reviewers or BUNDLED
    return {
        "outcome": "APPROVED",
        "counts": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
        "feedback": [],
        "reviewers": [{"reviewer": r, "outcome": "APPROVED"} for r in ids],
    }


def profile(reviewer):
    return ("---\nname: %s\ndescription: Reviews staged changes for %s concerns.\n---\n\n"
            "Check staged changes for %s concerns.\n") % (reviewer, reviewer, reviewer)


def write_profile(root, reviewer, content=None):
    """Drop a project-local reviewer profile under <root>/.agents/autoreview/reviewers/."""
    d = os.path.join(root, ".agents", "autoreview", "reviewers")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, reviewer + ".md"), "w", encoding="utf-8") as fh:
        fh.write(content if content is not None else profile(reviewer))
