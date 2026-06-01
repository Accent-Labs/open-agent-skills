from __future__ import annotations
import re
from typing import List, Optional
from .models import FileDelta, Flags

# ---------- shell-aware tokenization ----------


def split_segments(command: str) -> List[str]:
    segments: List[str] = []
    cur = ""
    quote: Optional[str] = None
    i, n = 0, len(command)
    while i < n:
        c = command[i]
        if quote:
            cur += c
            if c == quote:
                quote = None
            elif c == "\\" and quote == '"' and i + 1 < n:
                i += 1
                cur += command[i]
            i += 1
            continue
        if c in ("'", '"'):
            quote = c
            cur += c
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            cur += c + command[i + 1]
            i += 2
            continue
        two = command[i:i + 2]
        if two in ("&&", "||"):
            segments.append(cur)
            cur = ""
            i += 2
            continue
        if c in (";", "|", "&"):
            segments.append(cur)
            cur = ""
            i += 1
            continue
        cur += c
        i += 1
    segments.append(cur)
    return [s.strip() for s in segments if s.strip()]


def tokenize_segment(segment: str) -> List[str]:
    tokens: List[str] = []
    cur = ""
    quote: Optional[str] = None
    started = False
    i, n = 0, len(segment)
    while i < n:
        c = segment[i]
        if quote:
            if c == quote:
                quote = None
            elif c == "\\" and quote == '"' and i + 1 < n:
                i += 1
                cur += segment[i]
            else:
                cur += c
            i += 1
            continue
        if c in ("'", '"'):
            quote = c
            started = True
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            i += 1
            cur += segment[i]
            started = True
            i += 1
            continue
        if c in (" ", "\t"):
            if started:
                tokens.append(cur)
                cur = ""
                started = False
            i += 1
            continue
        cur += c
        started = True
        i += 1
    if started:
        tokens.append(cur)
    return tokens


# ---------- commit detection & flags ----------

_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
GIT_GLOBAL_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
GIT_INDEX_MUTATORS = {"add", "rm", "mv", "reset", "restore", "stash", "apply"}
_WRAPPERS = {"command", "builtin", "exec", "nohup"}  # simple single-token command wrappers
_ENV_VALUE_OPTS = {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}


def _strip_env(tokens: List[str]) -> List[str]:
    """tokens follow `env`; skip its options and NAME=VALUE assignments, return the command tokens."""
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "--":
            i += 1
            break
        if _ENV_ASSIGN.match(t):
            i += 1
            continue
        if t in _ENV_VALUE_OPTS:
            i += 2
            continue
        if t.startswith("-") and t != "-":
            i += 1
            continue
        break
    return tokens[i:]


def _unwrap(tokens: List[str]) -> List[str]:
    """Strip leading VAR=val assignments and simple wrappers (env, command, ...) so a git
    invocation hidden behind them is still detected."""
    changed = True
    while changed and tokens:
        changed = False
        while tokens and _ENV_ASSIGN.match(tokens[0]):
            tokens = tokens[1:]
            changed = True
        if tokens and tokens[0] == "env":
            tokens = _strip_env(tokens[1:])
            changed = True
        elif tokens and tokens[0] in _WRAPPERS:
            tokens = tokens[1:]
            changed = True
    return tokens


def _git_calls(command: str):
    """Yield (subcommand, arg_tokens) for each git invocation across all command segments,
    after unwrapping VAR=/env/wrappers and skipping git global options."""
    for seg in split_segments(command):
        tokens = _unwrap(tokenize_segment(seg))
        if not tokens or tokens[0] != "git":
            continue
        i = 1
        while i < len(tokens) and tokens[i].startswith("-"):
            i += 2 if tokens[i] in GIT_GLOBAL_VALUE_OPTS else 1
        if i < len(tokens):
            yield tokens[i], tokens[i + 1:]


def find_git_commit(command: str) -> Optional[List[str]]:
    """Arg tokens after `commit` for the FIRST git commit in the command, else None.
    Empty list = `git commit` with no args (distinct from None)."""
    for sub, args in _git_calls(command):
        if sub == "commit":
            return args
    return None


def scan_commits(command: str):
    """Return (commit_arg_lists, has_index_mutator). has_index_mutator is True when the command
    also runs a git command that changes the index/working tree (add/rm/mv/reset/...), so the
    staged tree the gate inspects may differ from what gets committed."""
    commits = []
    has_mutator = False
    for sub, args in _git_calls(command):
        if sub == "commit":
            commits.append(args)
        elif sub in GIT_INDEX_MUTATORS:
            has_mutator = True
    return commits, has_mutator


COMMIT_LONG_VALUE_OPTS = {
    "--message", "--file", "--author", "--date", "--template",
    "--reuse-message", "--reedit-message", "--fixup", "--squash", "--cleanup",
}
# `--pathspec-from-file` is handled explicitly (it commits the listed files, like a pathspec).
COMMIT_SHORT_VALUE_REQUIRED = "mFCct"   # -m -F -C -c -t : value is rest-of-cluster or next token
COMMIT_SHORT_VALUE_OPTIONAL = "uS"      # -u -S : optional value is the ATTACHED rest-of-cluster only


def parse_commit_flags(arg_tokens: List[str]) -> Flags:
    all_ = amend = no_verify = pathspec = interactive = False
    after_dd = False
    i = 0
    while i < len(arg_tokens):
        t = arg_tokens[i]
        if after_dd:
            pathspec = True
            i += 1
            continue
        if t == "--":
            after_dd = True
            i += 1
            continue
        if t.startswith("--"):
            name = t.split("=", 1)[0]
            if name == "--all":
                all_ = True
            elif name == "--amend":
                amend = True
            elif name == "--no-verify":
                no_verify = True
            elif name in ("--patch", "--interactive"):
                interactive = True
            elif name == "--pathspec-from-file":
                pathspec = True  # commits the files listed in the file, not just the staged tree
                if "=" not in t:
                    i += 1  # consume the path-file value
            elif name in COMMIT_LONG_VALUE_OPTS and "=" not in t:
                i += 1
            i += 1
            continue
        if t.startswith("-") and len(t) > 1:
            chars = t[1:]
            k = 0
            while k < len(chars):
                ch = chars[k]
                if ch == "a":
                    all_ = True
                elif ch == "n":
                    no_verify = True
                elif ch == "p":
                    interactive = True
                elif ch in COMMIT_SHORT_VALUE_REQUIRED:
                    if k == len(chars) - 1:
                        i += 1  # value is the next token
                    break       # rest of the cluster is the value
                elif ch in COMMIT_SHORT_VALUE_OPTIONAL:
                    break       # any attached value is the rest of the cluster; no next token
                # else: unknown boolean short flag -> ignore, keep scanning the cluster
                k += 1
            i += 1
            continue
        pathspec = True
        i += 1
    return Flags(all_, amend, no_verify, pathspec, interactive)


# ---------- numstat ----------


def _to_int(s: str) -> int:
    try:
        return int(s)
    except ValueError:
        return 0


def parse_numstat_z(buf: str) -> List[FileDelta]:
    parts = buf.split("\0")
    out: List[FileDelta] = []
    k = 0
    while k < len(parts):
        rec = parts[k]
        if rec == "":
            k += 1
            continue
        tab = rec.split("\t")
        if len(tab) < 3:
            k += 1
            continue
        binary = tab[0] == "-" and tab[1] == "-"
        added = 0 if binary else _to_int(tab[0])
        deleted = 0 if binary else _to_int(tab[1])
        path_field = "\t".join(tab[2:])
        if path_field == "":
            if k + 2 >= len(parts):
                break  # truncated rename record (real git never emits this); stop safely
            out.append(FileDelta(parts[k + 2], added, deleted, binary, "R", parts[k + 1]))
            k += 3
        else:
            out.append(FileDelta(path_field, added, deleted, binary, "M"))
            k += 1
    return out
