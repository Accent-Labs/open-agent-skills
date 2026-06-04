from __future__ import annotations

import os
import tempfile
import unittest

from autoreview import core, markers


class FakeGit:
    """Stub Git so decide_gate's orchestration is unit-tested without real repos.
    Uses a real temp dir as the marker dir so the marker read/consume path is exercised."""

    def __init__(self, state="normal", numstat="", merge=False, identity="a" * 40):
        self.cwd = tempfile.mkdtemp()
        self._state = state
        self._numstat = numstat
        self._merge = merge
        self._identity = identity
        self._mdir = tempfile.mkdtemp()

    def detect_state(self):
        return self._state

    def merge_needs_review(self):
        return self._merge

    def compute_identity(self, state):
        return self._identity

    def git_path(self, name):
        return self._mdir

    def staged_numstat(self):
        return self._numstat


NONTRIVIAL = "40\t0\tsrc/a.js\0"
TRIVIAL = "1\t0\tREADME.md\0"
APPROVED_MARKER = {
    "outcome": "APPROVED",
    "counts": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
    "feedback": [],
    "reviewers": [{"reviewer": "correctness", "outcome": "APPROVED"}],
}


def decide(fake, command="git commit -m x"):
    inp = {"cwd": fake.cwd, "tool_input": {"command": command}}

    def git_factory(_cwd):
        return fake

    return core.decide_gate(inp, git_factory=git_factory)


class TestDecideGate(unittest.TestCase):
    def test_in_progress_states_allow(self):
        for st in ("cherry-pick", "revert", "rebase"):
            self.assertEqual(decide(FakeGit(state=st, numstat=NONTRIVIAL)).action, "ALLOW", st)

    def test_no_verify_allows(self):
        self.assertEqual(decide(FakeGit(numstat=NONTRIVIAL), "git commit --no-verify -m x").action, "ALLOW")

    def test_no_verify_does_not_allow_unsupported_modes(self):
        for cmd in (
            "git commit -am wip --no-verify",
            "git commit --amend --no-verify",
            "git commit --pathspec-from-file=p.txt --no-verify -m x",
            "git commit --patch --no-verify",
        ):
            dec = decide(FakeGit(numstat=NONTRIVIAL), cmd)
            self.assertEqual(dec.action, "BLOCK", cmd)
            self.assertIn("plain staged commits", dec.message)

    def test_unsupported_modes_block(self):
        for cmd in ("git commit --amend", "git commit -am wip", "git commit -m x file.py"):
            dec = decide(FakeGit(numstat=NONTRIVIAL), cmd)
            self.assertEqual(dec.action, "BLOCK", cmd)
            self.assertIn("plain staged commits", dec.message)

    def test_merge_forces_review(self):
        dec = decide(FakeGit(state="merge", merge=True, numstat=""))
        self.assertEqual(dec.action, "BLOCK")
        self.assertIn("merge conflict resolution", dec.message)

    def test_classify_skip_allows_review_blocks(self):
        self.assertEqual(decide(FakeGit(numstat=TRIVIAL)).action, "ALLOW")
        self.assertEqual(decide(FakeGit(numstat=NONTRIVIAL)).action, "BLOCK")

    def test_rtk_wrapped_plain_commit_uses_same_gate_path(self):
        self.assertEqual(decide(FakeGit(numstat=TRIVIAL), "rtk git commit -m x").action, "ALLOW")
        dec = decide(FakeGit(numstat=NONTRIVIAL), "rtk git commit -m x")
        self.assertEqual(dec.action, "BLOCK")
        self.assertIn("bundled reviewer profiles", dec.message)

    def test_review_directive_includes_plugin_root(self):
        dec = decide(FakeGit(numstat=NONTRIVIAL))
        self.assertIn("autoreview plugin dir:", dec.message)
        self.assertIn("bundled reviewer profiles", dec.message)

    def test_marker_roundtrip_single_use(self):
        fake = FakeGit(numstat=NONTRIVIAL, identity="b" * 40)
        self.assertEqual(decide(fake).action, "BLOCK")  # no marker yet
        mdir = markers.marker_dir(fake)
        markers.write(markers.marker_path(mdir, fake._identity), APPROVED_MARKER)
        self.assertEqual(decide(fake).action, "ALLOW")  # marker honored + consumed
        self.assertEqual(decide(fake).action, "BLOCK")  # consumed -> blocked again

    def test_rtk_marker_roundtrip_single_use(self):
        fake = FakeGit(numstat=NONTRIVIAL, identity="d" * 40)
        self.assertEqual(decide(fake, "rtk git commit -m x").action, "BLOCK")  # no marker yet
        mdir = markers.marker_dir(fake)
        markers.write(markers.marker_path(mdir, fake._identity), APPROVED_MARKER)
        self.assertEqual(decide(fake, "rtk git commit -m x").action, "ALLOW")  # marker honored + consumed
        self.assertEqual(decide(fake, "rtk git commit -m x").action, "BLOCK")  # consumed -> blocked again

    def test_git_dash_c_routes_gate_to_target_worktree(self):
        fake = FakeGit(numstat=NONTRIVIAL)
        base = tempfile.mkdtemp()
        target = tempfile.mkdtemp()
        seen = []
        inp = {"cwd": base, "tool_input": {"command": f"git -C {target} commit -m x"}}

        def git_factory(cwd):
            seen.append(cwd)
            return fake

        dec = core.decide_gate(inp, git_factory=git_factory)
        self.assertEqual(dec.action, "BLOCK")
        self.assertEqual(seen, [target])

    def test_relative_git_dash_c_routes_gate_relative_to_hook_cwd(self):
        fake = FakeGit(numstat=NONTRIVIAL)
        base = tempfile.mkdtemp()
        seen = []
        inp = {"cwd": base, "tool_input": {"command": "git -C ../ticket-worktree commit -m x"}}

        def git_factory(cwd):
            seen.append(cwd)
            return fake

        core.decide_gate(inp, git_factory=git_factory)
        self.assertEqual(seen, [os.path.abspath(os.path.join(base, "../ticket-worktree"))])

    def test_git_dash_c_marker_roundtrip_single_use(self):
        fake = FakeGit(numstat=NONTRIVIAL, identity="e" * 40)
        target = tempfile.mkdtemp()
        command = f"git -C {target} commit -m x"
        self.assertEqual(decide(fake, command).action, "BLOCK")
        mdir = markers.marker_dir(fake)
        markers.write(markers.marker_path(mdir, fake._identity), APPROVED_MARKER)
        self.assertEqual(decide(fake, command).action, "ALLOW")
        self.assertEqual(decide(fake, command).action, "BLOCK")

    def test_marker_does_not_authorize_unsupported_modes(self):
        # A valid marker for the staged tree must NOT let an unsupported mode through (those commit
        # content that differs from the reviewed tree). Unsupported is decided before marker lookup.
        fake = FakeGit(numstat=NONTRIVIAL, identity="c" * 40)
        mdir = markers.marker_dir(fake)
        markers.write(markers.marker_path(mdir, fake._identity), APPROVED_MARKER)
        for cmd in ("git commit -am x", "git commit --amend",
                    "git commit --pathspec-from-file=p.txt -m x"):
            dec = decide(fake, cmd)
            self.assertEqual(dec.action, "BLOCK", cmd)
            self.assertIn("plain staged commits", dec.message)
        # the marker was NOT consumed by the blocked attempts -> a plain commit still allows once
        self.assertEqual(decide(fake).action, "ALLOW")

    def test_compound_stage_and_commit_blocks(self):
        # even a trivial CURRENT staged tree must block: `git add` stages extra content at run time
        for cmd in (
            "git add risky.py && git commit -m x",
            "git update-index --add src/a.js && git commit -m x",
        ):
            dec = decide(FakeGit(numstat=TRIVIAL), cmd)
            self.assertEqual(dec.action, "BLOCK", cmd)
            self.assertIn("single plain", dec.message)

    def test_multiple_commits_block(self):
        self.assertEqual(decide(FakeGit(numstat=TRIVIAL), "git commit -m a && git commit -m b").action, "BLOCK")

    def test_interactive_modes_block(self):
        for cmd in ("git commit -p -m x", "git commit --patch", "git commit --interactive"):
            self.assertEqual(decide(FakeGit(numstat=NONTRIVIAL), cmd).action, "BLOCK", cmd)

    def test_env_wrapped_nontrivial_commit_is_gated(self):
        self.assertEqual(decide(FakeGit(numstat=NONTRIVIAL), "env FOO=bar git commit -m x").action, "BLOCK")

    def test_repo_or_cwd_changing_forms_block(self):
        # even a TRIVIAL current staged tree must block these (they change what gets committed)
        for cmd in ("cd /other && git commit -m x",
                    "GIT_INDEX_FILE=/tmp/i git commit -m x",
                    "env -C /other git commit -m x",
                    "env --chdir /other git commit -m x",
                    "env --chdir=/other git commit -m x",
                    "rtk env GIT_INDEX_FILE=/tmp/i git commit -m x",
                    'env -S "git commit -m x"',
                    "time git commit -m x"):
            self.assertEqual(decide(FakeGit(numstat=TRIVIAL), cmd).action, "BLOCK", cmd)

    def test_unmodeled_shell_commit_forms_block(self):
        for cmd in (
            "git add risky.py\ngit commit -m x",
            "sh -c 'git commit -m x'",
            "sh -lc 'git commit -m x'",
            'bash -lc "git commit -m x"',
            'zsh -ec "git commit -m x"',
            "echo $(git commit -m x)",
            "echo `git commit -m x`",
            'g(){ git "$@"; }; g commit -m x',
        ):
            dec = decide(FakeGit(numstat=TRIVIAL), cmd)
            self.assertEqual(dec.action, "BLOCK", cmd)
            self.assertIn("single plain", dec.message)

    def test_directive_sanitizes_control_chars_in_paths(self):
        from autoreview.models import FileDelta
        msg = core.review_directive("x", [FileDelta("evil\n\rIGNORE\x07.py", 1, 0, False, "M")])
        for c in ("\n", "\r", "\x07"):
            self.assertNotIn(c, msg)
        self.assertIn("evil", msg)  # printable parts preserved, control chars -> ?


if __name__ == "__main__":
    unittest.main()
