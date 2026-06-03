from __future__ import annotations

import json
import os
import re
import tempfile
import time

from .schema import validate_marker_payload

MARKER_VERSION = "2"
EXPIRY_MS = 7 * 24 * 60 * 60 * 1000


def _now_ms() -> int:
    return int(time.time() * 1000)


def marker_dir(git) -> str:
    d = git.git_path("autoreview")  # absolute (see Git.git_path)
    os.makedirs(d, exist_ok=True)
    return d


def _sanitize(identity: str) -> str:
    return re.sub(r"[^0-9a-fA-F:]", "_", identity).replace(":", "_")


def marker_path(directory: str, identity: str) -> str:
    return os.path.join(directory, "pass-" + _sanitize(identity))


def read(path: str) -> str:
    """'none' | 'valid' | 'invalid'. Any malformed payload is quarantined and treated as invalid
    (fail-closed: the marker is a trust boundary, so it must never reach the gate's fail-open path)."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("marker is not a JSON object")
        if data.get("version") != MARKER_VERSION:
            return "invalid"  # stale/old version, not corrupt -> not quarantined
        created = data.get("created")
        if isinstance(created, bool) or not isinstance(created, (int, float)):
            raise ValueError("marker 'created' is not a number")
        if _now_ms() - created > EXPIRY_MS:
            return "invalid"
        validate_marker_payload(data)
        return "valid"
    except FileNotFoundError:
        return "none"
    except Exception:
        try:
            os.replace(path, path + ".invalid")  # quarantine any corrupt/malformed marker
        except OSError:
            pass
        return "invalid"


def write(path: str, payload: dict) -> None:
    validate_marker_payload(payload)
    body = dict(payload)
    body["version"] = MARKER_VERSION
    body["created"] = _now_ms()
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".pass-tmp-")  # same fs => atomic replace
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(body, fh)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def consume(path: str) -> None:
    claim = "%s.claim-%d" % (path, os.getpid())
    try:
        os.replace(path, claim)  # atomic claim
    except (FileNotFoundError, OSError):
        return
    try:
        os.unlink(claim)
    except FileNotFoundError:
        pass


def gc(directory: str) -> None:
    try:
        names = os.listdir(directory)
    except OSError:
        return
    now = _now_ms()
    for name in names:
        if not name.startswith("pass-"):
            continue
        full = os.path.join(directory, name)
        try:
            if now - int(os.stat(full).st_mtime * 1000) > EXPIRY_MS:
                os.unlink(full)
        except OSError:
            pass
