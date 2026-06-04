from __future__ import annotations
import unittest
from autoreview import diffparse as d
from autoreview.models import FileDelta, Flags


class TestTokenize(unittest.TestCase):
    def test_split(self):
        self.assertEqual(d.split_segments('a && b ; c | d'), ['a', 'b', 'c', 'd'])
        self.assertEqual(d.split_segments('git commit -m "a && b"'), ['git commit -m "a && b"'])
        self.assertEqual(d.split_segments("git commit -m 'x ; y'"), ["git commit -m 'x ; y'"])
        self.assertEqual(d.split_segments("git add x\ngit commit -m x"), ["git add x", "git commit -m x"])
        self.assertEqual(d.split_segments('git commit -m "line 1\nline 2"'), ['git commit -m "line 1\nline 2"'])

    def test_tokenize(self):
        self.assertEqual(d.tokenize_segment('git commit -m "a && b"'), ['git', 'commit', '-m', 'a && b'])
        self.assertEqual(d.tokenize_segment('VAR=val git commit'), ['VAR=val', 'git', 'commit'])
        self.assertEqual(d.tokenize_segment('git\ncommit\t-m x'), ['git', 'commit', '-m', 'x'])


class TestFindCommit(unittest.TestCase):
    def test(self):
        self.assertEqual(d.find_git_commit('git commit'), [])
        self.assertEqual(d.find_git_commit('git commit -m "msg"'), ['-m', 'msg'])
        self.assertEqual(d.find_git_commit('git -C /r -c a=b commit -m y'), ['-m', 'y'])
        self.assertEqual(d.find_git_commit('/usr/bin/git commit -m y'), ['-m', 'y'])
        self.assertEqual(d.find_git_commit('rtk git commit -m y'), ['-m', 'y'])
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
        # --pathspec-from-file commits the listed files -> pathspec (unsupported), both forms
        self.assertTrue(d.parse_commit_flags(['--pathspec-from-file=paths.txt']).pathspec)
        self.assertTrue(d.parse_commit_flags(['--pathspec-from-file', 'paths.txt']).pathspec)
        self.assertTrue(d.parse_commit_flags(['--pathspec-from-file', 'paths.txt', '-m', 'x']).pathspec)
        # optional-value short flags (-u/-S) must NOT be misread as -n (no-verify)
        self.assertFalse(d.parse_commit_flags(['-uno', '-m', 'x']).no_verify)
        self.assertFalse(d.parse_commit_flags(['-Sno', '-m', 'x']).no_verify)
        self.assertTrue(d.parse_commit_flags(['-u', '-n']).no_verify)  # separate -n still works
        # interactive modes (commit selected non-staged hunks)
        self.assertTrue(d.parse_commit_flags(['-p']).interactive)
        self.assertTrue(d.parse_commit_flags(['--patch']).interactive)
        self.assertTrue(d.parse_commit_flags(['--interactive']).interactive)


class TestScan(unittest.TestCase):
    def test_scan_commits_and_mutator(self):
        commits, mut = d.scan_commits('git add x && git commit -m y')
        self.assertEqual(commits, [['-m', 'y']])
        self.assertTrue(mut)  # `git add` is an index mutator
        commits, mut = d.scan_commits('git commit -m a && git commit -am b')
        self.assertEqual(len(commits), 2)
        self.assertFalse(mut)
        commits, mut = d.scan_commits('env FOO=bar git commit -m y')  # env-wrapped
        self.assertEqual(commits, [['-m', 'y']])
        self.assertEqual(d.scan_commits('command git commit')[0], [[]])  # wrapper-stripped
        self.assertEqual(d.scan_commits('rtk git commit -m y')[0], [['-m', 'y']])
        self.assertEqual(d.scan_commits('echo hi && ls')[0], [])  # no git commit


class TestNumstat(unittest.TestCase):
    def test(self):
        self.assertEqual(d.parse_numstat_z('3\t1\tsrc/a.js\0'),
                         [FileDelta('src/a.js', 3, 1, False, 'M')])
        self.assertEqual(d.parse_numstat_z('-\t-\timg.png\0'),
                         [FileDelta('img.png', 0, 0, True, 'M')])
        self.assertEqual(d.parse_numstat_z('5\t0\t\0old.js\0new.js\0'),
                         [FileDelta('new.js', 5, 0, False, 'R', 'old.js')])
        self.assertEqual(d.parse_numstat_z(''), [])

    def test_non_utf8_and_space_paths(self):
        weird = b"caf\xe9.txt".decode("utf-8", "surrogateescape")  # non-UTF-8 byte via surrogateescape
        self.assertEqual(d.parse_numstat_z("1\t0\t%s\0" % weird), [FileDelta(weird, 1, 0, False, "M")])
        self.assertEqual(d.parse_numstat_z("2\t1\tsrc/a b.js\0"),
                         [FileDelta("src/a b.js", 2, 1, False, "M")])

    def test_truncated_rename_record_is_safe(self):
        self.assertEqual(d.parse_numstat_z("5\t0\t\0old.js"), [])  # missing newpath -> drop, no crash


class TestUnsafe(unittest.TestCase):
    def test_safe_shapes(self):
        self.assertEqual(d.analyze_command("git commit -m x"), ([["-m", "x"]], False, False, True))
        self.assertEqual(d.analyze_command("/usr/bin/git commit -m x"), ([["-m", "x"]], False, False, True))
        self.assertEqual(d.analyze_command("echo done && git commit -m x"), ([["-m", "x"]], False, False, True))
        self.assertEqual(d.analyze_command("env FOO=bar git commit -m x"), ([["-m", "x"]], False, False, True))
        self.assertEqual(d.analyze_command("rtk git commit -m x"), ([["-m", "x"]], False, False, True))
        self.assertEqual(d.analyze_command("rtk /usr/bin/git commit -m x"), ([["-m", "x"]], False, False, True))
        self.assertEqual(d.analyze_command("ls -la"), ([], False, False, False))

    def test_git_dash_c_commit_targets_are_safe_for_direct_commits(self):
        analysis = d.analyze_command("git -C /work/tree commit -m x")
        self.assertEqual(analysis.commits, [["-m", "x"]])
        self.assertFalse(analysis.has_mutator)
        self.assertFalse(analysis.unsafe)
        self.assertTrue(analysis.has_commit)
        self.assertEqual(analysis.target_cwd, "/work/tree")

        analysis = d.analyze_command("rtk git -C ../ticket-worktree commit -m x")
        self.assertEqual(analysis.commits, [["-m", "x"]])
        self.assertFalse(analysis.unsafe)
        self.assertEqual(analysis.target_cwd, "../ticket-worktree")

    def test_git_dash_c_with_other_repo_redirects_remains_unsafe(self):
        for cmd in (
            "git -C /work/tree --work-tree=/elsewhere commit -m x",
            "git -C /work/tree --git-dir=/elsewhere/.git commit -m x",
            "git -C /work -C tree commit -m x",
        ):
            analysis = d.analyze_command(cmd)
            self.assertEqual(analysis.commits, [["-m", "x"]], cmd)
            self.assertTrue(analysis.unsafe, cmd)
            self.assertTrue(analysis.has_commit, cmd)
            self.assertIsNone(analysis.target_cwd, cmd)

    def test_repo_or_cwd_changing_forms_are_unsafe(self):
        for cmd in ("cd /other && git commit -m x",
                    "git --git-dir=/x/.git commit -m x",
                    "git --work-tree=/x commit -m x",
                    "GIT_INDEX_FILE=/tmp/i git commit -m x",
                    "GIT_DIR=/x git commit -m x",
                    "env GIT_DIR=/x git commit -m x",
                    "env -C /other git commit -m x",
                    "env --chdir /other git commit -m x",
                    "env --chdir=/other git commit -m x",
                    "rtk env GIT_INDEX_FILE=/tmp/i git commit -m x",
                    'env -S "git commit -m x"',
                    "time git commit -m x",
                    "sudo git commit -m x",
                    "sh -c 'git -c user.name=t commit -m x'",
                    "echo $(/usr/bin/git commit -m x)"):
            _, _, unsafe, has_commit = d.analyze_command(cmd)
            self.assertTrue(unsafe, cmd)
            self.assertTrue(has_commit, cmd)

    def test_quoted_text_is_not_a_commit(self):
        self.assertEqual(d.analyze_command('echo "git commit"'), ([], False, False, False))
        _, _, _, has_commit = d.analyze_command('env -S "echo hi"')
        self.assertFalse(has_commit)  # env -S without a git commit -> not gated

    def test_newline_separated_commit_is_detected(self):
        commits, mut, unsafe, has_commit = d.analyze_command("git add x\ngit commit -m x")
        self.assertEqual(commits, [["-m", "x"]])
        self.assertTrue(mut)
        self.assertFalse(unsafe)
        self.assertTrue(has_commit)

    def test_nested_shell_and_substitution_commit_forms_are_unsafe(self):
        for cmd in (
            "sh -c 'git commit -m x'",
            "sh -c 'git -c user.name=t commit -m x'",
            "sh -lc 'git commit -m x'",
            'bash -c "git commit -m x"',
            'bash -lc "git commit -m x"',
            'zsh -c "git commit -m x"',
            'zsh -ec "git commit -m x"',
            "eval 'git commit -m x'",
            "echo $(git commit -m x)",
            "echo $(/usr/bin/git commit -m x)",
            "echo `git commit -m x`",
            'g(){ git "$@"; }; g commit -m x',
            "sudo git commit -m x",
        ):
            _, _, unsafe, has_commit = d.analyze_command(cmd)
            self.assertTrue(unsafe, cmd)
            self.assertTrue(has_commit, cmd)

    def test_non_read_only_git_before_commit_counts_as_mutator(self):
        for cmd in (
            "git update-index --add src/a.js && git commit -m x",
            "git checkout -- src/a.js && git commit -m x",
        ):
            commits, mut, unsafe, has_commit = d.analyze_command(cmd)
            self.assertEqual(commits, [["-m", "x"]], cmd)
            self.assertTrue(mut, cmd)
            self.assertFalse(unsafe, cmd)
            self.assertTrue(has_commit, cmd)

    def test_read_only_git_before_commit_does_not_count_as_mutator(self):
        commits, mut, unsafe, has_commit = d.analyze_command("git status && git commit -m x")
        self.assertEqual(commits, [["-m", "x"]])
        self.assertFalse(mut)
        self.assertFalse(unsafe)
        self.assertTrue(has_commit)


if __name__ == '__main__':
    unittest.main()
