from __future__ import annotations
import os
import subprocess
import tempfile
import unittest
from autoreview.gitcmd import Git


def mkrepo():
    d = tempfile.mkdtemp(prefix="ar-")
    run = lambda *a: subprocess.run(["git", *a], cwd=d, capture_output=True, text=True, check=True)  # noqa: E731
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    run("commit", "--allow-empty", "-q", "-m", "root")
    return d, run


def write(path, content):
    with open(path, "w") as fh:
        fh.write(content)


class TestGit(unittest.TestCase):
    def test_state_and_identity(self):
        d, run = mkrepo()
        g = Git(d)
        self.assertEqual(g.detect_state(), "normal")
        write(os.path.join(d, "x.txt"), "hi\n")
        run("add", "x.txt")
        self.assertRegex(g.compute_identity("normal"), r"^[0-9a-f]{40}$")

    def test_merge_needs_review(self):
        d, run = mkrepo()
        run("checkout", "-q", "-b", "feature")
        write(os.path.join(d, "c.txt"), "feature\n")
        run("add", "c.txt")
        run("commit", "-q", "-m", "f")
        run("checkout", "-q", "main")
        write(os.path.join(d, "c.txt"), "main\n")
        run("add", "c.txt")
        run("commit", "-q", "-m", "m")
        try:
            run("merge", "-q", "feature")
        except subprocess.CalledProcessError:
            pass
        write(os.path.join(d, "c.txt"), "hand\n")
        run("add", "c.txt")
        g = Git(d)
        self.assertEqual(g.detect_state(), "merge")
        self.assertTrue(g.merge_needs_review())

    def test_clean_merge_does_not_force_review(self):
        d, run = mkrepo()
        write(os.path.join(d, "base.txt"), "base\n"); run("add", "base.txt"); run("commit", "-q", "-m", "base")
        run("checkout", "-q", "-b", "feature")
        write(os.path.join(d, "f.txt"), "feature\n"); run("add", "f.txt"); run("commit", "-q", "-m", "f")
        run("checkout", "-q", "main")
        write(os.path.join(d, "m.txt"), "main\n"); run("add", "m.txt"); run("commit", "-q", "-m", "m")
        try:
            run("merge", "--no-commit", "--no-ff", "feature")  # non-conflicting; pause before commit
        except subprocess.CalledProcessError:
            pass
        g = Git(d)
        self.assertEqual(g.detect_state(), "merge")
        self.assertFalse(g.merge_needs_review())  # clean merge -> no hand resolution -> no review

    def test_merge_with_staged_conflict_markers_is_reviewed(self):
        d, run = mkrepo()
        run("checkout", "-q", "-b", "feature")
        write(os.path.join(d, "c.txt"), "feature\n"); run("add", "c.txt"); run("commit", "-q", "-m", "f")
        run("checkout", "-q", "main")
        write(os.path.join(d, "c.txt"), "main\n"); run("add", "c.txt"); run("commit", "-q", "-m", "m")
        try:
            run("merge", "-q", "feature")
        except subprocess.CalledProcessError:
            pass
        run("add", "c.txt")  # stage the conflicted file WITH markers intact (index == AUTO_MERGE)
        g = Git(d)
        self.assertEqual(g.detect_state(), "merge")
        self.assertTrue(g.merge_needs_review())  # leftover conflict markers -> must review


if __name__ == "__main__":
    unittest.main()
