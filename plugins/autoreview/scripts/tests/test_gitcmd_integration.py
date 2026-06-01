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


if __name__ == "__main__":
    unittest.main()
