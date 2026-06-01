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


class TestGit(unittest.TestCase):
    def test_state_and_identity(self):
        d, run = mkrepo()
        g = Git(d)
        self.assertEqual(g.detect_state(), "normal")
        open(os.path.join(d, "x.txt"), "w").write("hi\n")
        run("add", "x.txt")
        self.assertRegex(g.compute_identity("normal"), r"^[0-9a-f]{40}$")

    def test_merge_needs_review(self):
        d, run = mkrepo()
        run("checkout", "-q", "-b", "feature")
        open(os.path.join(d, "c.txt"), "w").write("feature\n")
        run("add", "c.txt")
        run("commit", "-q", "-m", "f")
        run("checkout", "-q", "main")
        open(os.path.join(d, "c.txt"), "w").write("main\n")
        run("add", "c.txt")
        run("commit", "-q", "-m", "m")
        try:
            run("merge", "-q", "feature")
        except subprocess.CalledProcessError:
            pass
        open(os.path.join(d, "c.txt"), "w").write("hand\n")
        run("add", "c.txt")
        g = Git(d)
        self.assertEqual(g.detect_state(), "merge")
        self.assertTrue(g.merge_needs_review())

    def test_clean_merge_does_not_force_review(self):
        d, run = mkrepo()
        open(os.path.join(d, "base.txt"), "w").write("base\n"); run("add", "base.txt"); run("commit", "-q", "-m", "base")
        run("checkout", "-q", "-b", "feature")
        open(os.path.join(d, "f.txt"), "w").write("feature\n"); run("add", "f.txt"); run("commit", "-q", "-m", "f")
        run("checkout", "-q", "main")
        open(os.path.join(d, "m.txt"), "w").write("main\n"); run("add", "m.txt"); run("commit", "-q", "-m", "m")
        try:
            run("merge", "--no-commit", "--no-ff", "feature")  # non-conflicting; pause before commit
        except subprocess.CalledProcessError:
            pass
        g = Git(d)
        self.assertEqual(g.detect_state(), "merge")
        self.assertFalse(g.merge_needs_review())  # clean merge -> no hand resolution -> no review


if __name__ == "__main__":
    unittest.main()
