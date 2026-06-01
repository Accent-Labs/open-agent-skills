from __future__ import annotations
import argparse
import json
import os
import sys
from . import diffparse, markers
from .core import decide_gate
from .gitcmd import Git
from .models import BLOCK


def _warn(msg: str) -> None:
    sys.stderr.write(f"[autoreview] {msg}\n")


def _do_mark(payload_json: str) -> None:
    git = Git(os.getcwd())
    identity = git.compute_identity(git.detect_state())
    mdir = markers.marker_dir(git)
    try:
        payload = json.loads(payload_json or "{}")
    except ValueError:
        payload = {}
    markers.write(markers.marker_path(mdir, identity), payload)
    sys.stdout.write(f"marker written for {identity}\n")


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    # Route subcommands without building argparse on the stdin-gate hot path.
    if argv and argv[0] == "mark":
        parser = argparse.ArgumentParser(prog="gate.py mark")
        parser.add_argument("--payload", default="{}")
        args = parser.parse_args(argv[1:])
        try:
            _do_mark(args.payload)
        except Exception as e:  # mark failures must not crash the agent's flow
            _warn(f"mark failed ({e})")
        return

    raw = sys.stdin.read()
    try:
        inp = json.loads(raw)
    except Exception as e:
        _warn(f"malformed hook input; allowing ({e})")
        sys.exit(0)
    try:
        decision = decide_gate(inp)
    except Exception as e:  # THE fail-open boundary
        _warn(f"internal error; allowing ({e})")
        sys.exit(0)
    if decision.action == BLOCK:
        sys.stderr.write(decision.message + "\n")
        sys.exit(2)
    cmd = (inp.get("tool_input") or {}).get("command", "") or ""
    commit_args = diffparse.find_git_commit(cmd)
    if commit_args is not None and diffparse.parse_commit_flags(commit_args).no_verify:
        _warn("commit uses --no-verify; autoreview bypassed")
    sys.exit(0)
