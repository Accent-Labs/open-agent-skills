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
_GIT_ENV = re.compile(r"^GIT_[A-Za-z0-9_]*=")  # GIT_DIR/GIT_INDEX_FILE/GIT_WORK_TREE/... redirect git
GIT_GLOBAL_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
GIT_INDEX_MUTATORS = {"add", "rm", "mv", "reset", "restore", "stash", "apply"}
_WRAPPERS = {"command", "builtin", "exec", "nohup"}     # transparent single-token wrappers we can model
_CD_COMMANDS = {"cd", "pushd", "popd", "chdir"}         # change the working directory
_REPO_REDIRECT_GLOBALS = {"-C", "--git-dir", "--work-tree"}  # git globals that change repo/cwd/worktree
_ENV_SPLIT_OPTS = ("-S", "--split-string")


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
        if t in ("-u", "--unset", "-C", "--chdir", "-S", "--split-string"):
            i += 2
            continue
        if t.startswith("-") and t != "-":
            i += 1
            continue
        break
    return tokens[i:]


def _wrapped_git_commit(tokens: List[str]) -> bool:
    """True if `git ... commit` appears as command tokens in this segment behind an unmodelable
    wrapper (e.g. time / sudo / xargs). Token-based, so `echo "git commit"` (one quoted token) is
    NOT matched."""
    for j in range(len(tokens) - 1):
        if tokens[j] == "git":
            k = j + 1
            while k < len(tokens) and tokens[k].startswith("-"):
                k += 2 if tokens[k] in GIT_GLOBAL_VALUE_OPTS else 1
            if k < len(tokens) and tokens[k] == "commit":
                return True
    return False


def _env_split_value(rest: List[str]) -> Optional[str]:
    """Return the command STRING of `env -S/--split-string <STR>` (or attached forms), else None."""
    for j, t in enumerate(rest):
        if t in _ENV_SPLIT_OPTS:
            return rest[j + 1] if j + 1 < len(rest) else ""
        if t.startswith("--split-string="):
            return t.split("=", 1)[1]
        if t.startswith("-S") and len(t) > 2:
            return t[2:]
    return None


def analyze_command(command: str):
    """Classify a Bash command for the gate. Returns (commits, has_mutator, unsafe, has_commit):

    - commits: arg-token-lists for each cleanly-parsed DIRECT `git commit` (first token `git`).
    - has_mutator: a git index-mutating command co-occurs (add/rm/mv/reset/...).
    - unsafe: the command changes cwd/repo/index or wraps the commit unmodelably (cd/pushd,
      `git -C`/`--git-dir`/`--work-tree`, GIT_* env, `env -S`, time/sudo/unknown wrappers).
    - has_commit: a git commit is present anywhere (direct OR behind a wrapper / env -S).

    The allow-shape is intentionally narrow: exactly one cleanly-parsed plain commit with `unsafe`
    and `has_mutator` both False. Anything else blocks (we do not partially model shell execution).
    """
    commits: List[List[str]] = []
    has_mutator = False
    unsafe = False
    has_commit = False
    for seg in split_segments(command):
        tokens = tokenize_segment(seg)
        # leading env assignments: benign unless they redirect git (GIT_DIR/GIT_INDEX_FILE/...)
        while tokens and _ENV_ASSIGN.match(tokens[0]):
            if _GIT_ENV.match(tokens[0]):
                unsafe = True
            tokens = tokens[1:]
        # strip transparent wrappers we can fully model
        while tokens and tokens[0] in _WRAPPERS:
            tokens = tokens[1:]
        if not tokens:
            continue
        head = tokens[0]
        if head in _CD_COMMANDS:
            unsafe = True
            continue
        if head == "env":
            rest = tokens[1:]
            sval = _env_split_value(rest)
            if sval is not None:
                unsafe = True  # env -S runs a command STRING we don't model
                if _wrapped_git_commit(tokenize_segment(sval)):
                    has_commit = True
                continue
            inner = _strip_env(rest)
            if any(_GIT_ENV.match(t) for t in rest[: len(rest) - len(inner)]):
                unsafe = True  # GIT_* assignment passed through env
            tokens = inner
            head = tokens[0] if tokens else ""
        if head != "git":
            if _wrapped_git_commit(tokens):
                unsafe = True  # git commit behind an unmodelable wrapper (time/sudo/...)
                has_commit = True
            continue
        # direct git invocation: walk global options
        i = 1
        while i < len(tokens) and tokens[i].startswith("-"):
            if tokens[i].split("=", 1)[0] in _REPO_REDIRECT_GLOBALS:
                unsafe = True
            i += 2 if tokens[i] in GIT_GLOBAL_VALUE_OPTS else 1
        if i < len(tokens):
            sub = tokens[i]
            if sub == "commit":
                commits.append(tokens[i + 1:])
                has_commit = True
            elif sub in GIT_INDEX_MUTATORS:
                has_mutator = True
    return commits, has_mutator, unsafe, has_commit


def scan_commits(command: str):
    """Back-compat: (commits, has_mutator)."""
    commits, has_mutator, _, _ = analyze_command(command)
    return commits, has_mutator


def find_git_commit(command: str) -> Optional[List[str]]:
    """Arg tokens after `commit` for the FIRST git commit, else None.
    Empty list = `git commit` with no args (distinct from None)."""
    commits, _, _, _ = analyze_command(command)
    return commits[0] if commits else None


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
