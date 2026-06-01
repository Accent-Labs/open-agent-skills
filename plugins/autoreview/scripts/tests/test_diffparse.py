from __future__ import annotations
import unittest
from autoreview import diffparse as d
from autoreview.models import FileDelta, Flags


class TestTokenize(unittest.TestCase):
    def test_split(self):
        self.assertEqual(d.split_segments('a && b ; c | d'), ['a', 'b', 'c', 'd'])
        self.assertEqual(d.split_segments('git commit -m "a && b"'), ['git commit -m "a && b"'])
        self.assertEqual(d.split_segments("git commit -m 'x ; y'"), ["git commit -m 'x ; y'"])

    def test_tokenize(self):
        self.assertEqual(d.tokenize_segment('git commit -m "a && b"'), ['git', 'commit', '-m', 'a && b'])
        self.assertEqual(d.tokenize_segment('VAR=val git commit'), ['VAR=val', 'git', 'commit'])


class TestFindCommit(unittest.TestCase):
    def test(self):
        self.assertEqual(d.find_git_commit('git commit'), [])
        self.assertEqual(d.find_git_commit('git commit -m "msg"'), ['-m', 'msg'])
        self.assertEqual(d.find_git_commit('git -C /r -c a=b commit -m y'), ['-m', 'y'])
        self.assertEqual(d.find_git_commit('VAR=1 git commit --amend'), ['--amend'])
        self.assertEqual(d.find_git_commit('echo hi && git commit'), [])
        self.assertIsNone(d.find_git_commit('git commit-tree abc'))
        self.assertIsNone(d.find_git_commit('npm run commit'))
        self.assertIsNone(d.find_git_commit('git status'))


class TestFlags(unittest.TestCase):
    def test(self):
        self.assertEqual(d.parse_commit_flags([]), Flags())
        self.assertFalse(d.parse_commit_flags(['-m', 'hello']).pathspec)
        self.assertTrue(d.parse_commit_flags(['-a']).all)
        self.assertTrue(d.parse_commit_flags(['-am', 'msg']).all)
        self.assertTrue(d.parse_commit_flags(['--amend']).amend)
        self.assertTrue(d.parse_commit_flags(['--no-verify']).no_verify)
        self.assertTrue(d.parse_commit_flags(['-n']).no_verify)
        self.assertTrue(d.parse_commit_flags(['-m', 'x', 'src/foo.js']).pathspec)
        self.assertFalse(d.parse_commit_flags(['-m', 'commit']).pathspec)
        self.assertTrue(d.parse_commit_flags(['--', 'file.txt']).pathspec)


class TestNumstat(unittest.TestCase):
    def test(self):
        self.assertEqual(d.parse_numstat_z('3\t1\tsrc/a.js\0'),
                         [FileDelta('src/a.js', 3, 1, False, 'M')])
        self.assertEqual(d.parse_numstat_z('-\t-\timg.png\0'),
                         [FileDelta('img.png', 0, 0, True, 'M')])
        self.assertEqual(d.parse_numstat_z('5\t0\t\0old.js\0new.js\0'),
                         [FileDelta('new.js', 5, 0, False, 'R', 'old.js')])
        self.assertEqual(d.parse_numstat_z(''), [])


if __name__ == '__main__':
    unittest.main()
