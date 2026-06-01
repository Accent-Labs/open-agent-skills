from __future__ import annotations
import unittest
from autoreview.classify import classify
from autoreview.models import FileDelta


def fd(path, added=5, deleted=0, binary=False):
    return FileDelta(path, added, deleted, binary, "M")


class TestClassify(unittest.TestCase):
    def test_precedence(self):
        self.assertEqual(classify([]).action, "SKIP")
        self.assertEqual(classify([fd("package-lock.json", 1)]).action, "REVIEW")
        self.assertEqual(classify([fd(".github/workflows/ci.yml", 1)]).action, "REVIEW")
        self.assertEqual(classify([fd("docs/auth/login.md", 1)]).action, "REVIEW")
        self.assertEqual(classify([fd("logo.png", 0, 0, True)]).action, "REVIEW")
        self.assertEqual(classify([fd("dist/bundle.js", 999)]).action, "SKIP")
        self.assertEqual(classify([fd("app.min.js", 999)]).action, "SKIP")
        self.assertEqual(classify([fd("README.md", 50)]).action, "SKIP")
        self.assertEqual(classify([fd("src/a.js", 5, 4)]).action, "SKIP")
        self.assertEqual(classify([fd("src/a.js", 30)]).action, "REVIEW")


if __name__ == "__main__":
    unittest.main()
