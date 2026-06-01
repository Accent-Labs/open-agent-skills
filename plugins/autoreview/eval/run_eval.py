from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fixtures import FIXTURES  # noqa: E402

GATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "gate.py")


def new_repo():
    d = tempfile.mkdtemp(prefix="areval-")
    g = lambda *a: subprocess.run(["git", *a], cwd=d, capture_output=True, text=True, check=True).stdout  # noqa: E731
    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    g("commit", "--allow-empty", "-q", "-m", "root")
    return d, g


def _put(d, content):
    with open(os.path.join(d, "c.txt"), "w") as fh:
        fh.write(content)


def build_merge(d, g):
    g("checkout", "-q", "-b", "feature")
    _put(d, "feature\n")
    g("add", "c.txt")
    g("commit", "-q", "-m", "f")
    g("checkout", "-q", "main")
    _put(d, "main\n")
    g("add", "c.txt")
    g("commit", "-q", "-m", "m")
    try:
        g("merge", "-q", "feature")
    except subprocess.CalledProcessError:
        pass
    _put(d, "hand\n")
    g("add", "c.txt")


def run_gate(d, command):
    payload = json.dumps({"cwd": d, "tool_input": {"command": command}})
    p = subprocess.run(["python3", GATE], input=payload, cwd=d, capture_output=True, text=True)
    return p.returncode, p.stderr


class TestGate(unittest.TestCase):
    pass


def _mk(name, cmd, setup, expect):
    def test(self):
        d, g = new_repo()
        if setup == "MERGE":
            build_merge(d, g)
        else:
            setup(d, g)
        code, err = run_gate(d, cmd)
        if expect == "ALLOW":
            self.assertEqual(code, 0, err)
        else:
            self.assertEqual(code, 2, "expected block, got %d (%s)" % (code, err))
            pat = (r"(?i)stage your changes explicitly|plain staged commits"
                   if expect == "UNSUPPORTED" else r"(?i)autoreview required|review")
            self.assertRegex(err, pat)
    return test


for _i, (_n, _c, _s, _e) in enumerate(FIXTURES):
    setattr(TestGate, "test_%02d_%s" % (_i, _n.split("-")[0]), _mk(_n, _c, _s, _e))


if __name__ == "__main__":
    unittest.main()
