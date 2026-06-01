import os


def w(d, rel, content):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(content)


def trivial(d, g):
    w(d, "a.txt", "one\ntwo\n")
    g("add", "a.txt")


def nontrivial(d, g):
    w(d, "src/a.js", "\n".join("const x%d=%d;" % (i, i) for i in range(40)) + "\n")
    g("add", "src/a.js")


def lockfile(d, g):
    w(d, "package-lock.json", '{"a":1}\n')
    g("add", "package-lock.json")


def docs(d, g):
    w(d, "README.md", "a\n" * 50)
    g("add", "README.md")


def big(d, g):
    w(d, "src/big.js", "x\n" * 80)
    g("add", "src/big.js")


def amp(d, g):
    w(d, "a.txt", "hi\n")
    g("add", "a.txt")


def dasha(d, g):
    w(d, "src/a.js", "x\n" * 40)
    g("add", "src/a.js")
    open(os.path.join(d, "src/a.js"), "a").write("y\n")


def amend(d, g):
    w(d, "src/a.js", "x\n" * 40)
    g("add", "src/a.js")


def noverify(d, g):
    w(d, "src/a.js", "x\n" * 40)
    g("add", "src/a.js")


def cherry(d, g):
    open(os.path.join(d, ".git", "CHERRY_PICK_HEAD"), "w").write("dead\n")
    w(d, "src/a.js", "x\n" * 40)
    g("add", "src/a.js")


FIXTURES = [
    ("trivial->allow", "git commit -m x", trivial, "ALLOW"),
    ("nontrivial->review", "git commit -m x", nontrivial, "REVIEW"),
    ("lockfile->review", "git commit -m x", lockfile, "REVIEW"),
    ("docs->allow", "git commit -m x", docs, "ALLOW"),
    ("committree->allow", "git commit-tree abc", big, "ALLOW"),
    ("ampmsg->allow", 'git commit -m "fix a && b"', amp, "ALLOW"),
    ("dasha->unsupported", "git commit -am wip", dasha, "UNSUPPORTED"),
    ("amend->unsupported", "git commit --amend", amend, "UNSUPPORTED"),
    ("noverify->allow", "git commit --no-verify -m x", noverify, "ALLOW"),
    ("merge->review", "git commit -m merge", "MERGE", "REVIEW"),
    ("cherry->allow", "git commit -m x", cherry, "ALLOW"),
]
