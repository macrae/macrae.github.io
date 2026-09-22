"""Prove the validator by re-introducing each bug it exists for.

A validator nobody has seen fail is a validator nobody knows works. The other
half matters just as much: a clean tree must produce ZERO errors, or the check
fires on correct data and is worse than nothing.
"""

import pathlib
import shutil
import tempfile

import pytest

from sitegen import build, validate


@pytest.fixture
def tree(corpus):
    root = pathlib.Path(tempfile.mkdtemp())
    build.write(build.plan(corpus), root=root)
    yield root
    shutil.rmtree(root)


def run(root, corpus):
    report = validate.Report()
    validate.check_tree(root, corpus, report)
    return report


def test_a_clean_tree_produces_zero_errors(tree, corpus):
    report = run(tree, corpus)
    assert report.errors == [], f"fires on correct data: {report.errors[:3]}"


def _inject(tree, fragment):
    page = tree / "index.html"
    page.write_text(page.read_text(encoding="utf-8").replace("</body>", fragment + "</body>"),
                    encoding="utf-8")


@pytest.mark.parametrize("fragment,expect", [
    ('<script src="evil.js"></script><noscript>x</noscript>', "undeclared script"),
    ('<script>alert(1)</script><noscript>x</noscript>',       "inline <script> body"),
    ('<script src="https://cdn.example.com/x.js"></script><noscript>x</noscript>',
     "remote script"),
    ('<div onclick="go()">x</div>',                            "inline event handler"),
    ('<a href="javascript:void(0)">x</a>',                     "javascript: URL"),
    ('<img src="nope.png">',                                   "has no alt"),
    ('<a href="/does-not-exist/">x</a>',                       "broken link"),
    ('<a href="#nowhere">x</a>',                               "no matching id"),
])
def test_each_injected_fault_is_caught(tree, corpus, fragment, expect):
    _inject(tree, fragment)
    report = run(tree, corpus)
    assert any(expect in e for e in report.errors), (
        f"{expect!r} not caught; got {report.errors}")


def test_a_script_with_no_noscript_is_caught(tree, corpus):
    _inject(tree, '<script src="x.js"></script>')
    assert any("no <noscript>" in e for e in run(tree, corpus).errors)


def test_a_missing_cname_is_caught(tree, corpus):
    (tree / "CNAME").unlink()
    assert any("CNAME" in e for e in run(tree, corpus).errors)


def test_a_wrong_cname_is_caught(tree, corpus):
    (tree / "CNAME").write_text("example.com\n")
    assert any("expected" in e for e in run(tree, corpus).errors)


def test_a_missing_nojekyll_is_caught(tree, corpus):
    (tree / ".nojekyll").unlink()
    assert any("Jekyll" in e for e in run(tree, corpus).errors)


def test_a_hand_edited_stylesheet_is_caught(tree, corpus):
    css = tree / "site.css"
    css.write_text(css.read_text(encoding="utf-8") + "\n.hand{color:red}\n",
                   encoding="utf-8")
    assert any("hand-edited" in e for e in run(tree, corpus).errors)


def test_the_external_repo_allowlist_has_exactly_one_entry():
    """/mana-map/ is the only link that may not resolve inside this tree. A
    second entry means somebody widened the hole rather than fixing a link."""
    assert validate.EXTERNAL_REPO_PATHS == ("/mana-map/",)
