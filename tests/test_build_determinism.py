"""The central claim: the same content produces the same bytes."""

import pathlib
import shutil
import tempfile

from sitegen import build, content


def _build(root, corpus):
    build.write(build.plan(corpus), root=root)
    return {str(p.relative_to(root)): p.read_bytes()
            for p in root.rglob("*") if p.is_file()}


def test_two_builds_are_byte_identical(corpus):
    a, b = (pathlib.Path(tempfile.mkdtemp()) for _ in range(2))
    try:
        fa, fb = _build(a, corpus), _build(b, corpus)
        assert set(fa) == set(fb), f"path sets differ: {set(fa) ^ set(fb)}"
        differing = [k for k in fa if fa[k] != fb[k]]
        assert not differing, f"{len(differing)} files differ: {differing[:5]}"
        assert len(fa) >= 10, f"only {len(fa)} files built"
    finally:
        shutil.rmtree(a); shutil.rmtree(b)


def test_the_committed_tree_matches_what_content_renders_to(repo):
    """The in-suite twin of the CI gate, so a stale docs/ is caught locally
    before the push rather than in a red pipeline."""
    published = content.load()
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        fresh = _build(tmp, published)
        committed = {str(p.relative_to(repo / "docs")): p.read_bytes()
                     for p in (repo / "docs").rglob("*") if p.is_file()}
        missing = sorted(set(fresh) - set(committed))
        extra = sorted(set(committed) - set(fresh))
        assert not missing, f"docs/ is missing {missing[:5]} — run `make site`"
        assert not extra, f"docs/ has orphans {extra[:5]} — run `make site`"
        stale = [k for k in fresh if fresh[k] != committed[k]]
        assert not stale, f"docs/ is stale: {stale[:5]} — run `make site` and commit"
    finally:
        shutil.rmtree(tmp)


def test_prune_removes_an_orphan_that_git_diff_would_never_see(corpus):
    """A renamed slug leaves docs/old-slug/index.html behind. `git diff` is
    blind to it, which is why the build prunes and CI also checks
    `git status --porcelain`."""
    root = pathlib.Path(tempfile.mkdtemp())
    try:
        build.write(build.plan(corpus), root=root)
        orphan = root / "old-slug" / "index.html"
        orphan.parent.mkdir(parents=True)
        orphan.write_text("stale")
        _, removed = build.write(build.plan(corpus), root=root)
        assert "old-slug/index.html" in removed
        assert not (root / "old-slug").exists(), "the empty directory survived"
    finally:
        shutil.rmtree(root)


def test_pinned_files_survive_pruning(corpus):
    root = pathlib.Path(tempfile.mkdtemp())
    try:
        build.write(build.plan(corpus), root=root)
        assert (root / "CNAME").read_text().strip() == "seanmacrae.com"
        assert (root / ".nojekyll").exists()
    finally:
        shutil.rmtree(root)


def test_no_page_carries_a_build_date(corpus):
    """A page stamped with 'now' changes on every build and destroys the
    byte-identical rebuild claim."""
    import datetime
    today = datetime.date.today().isoformat()
    root = pathlib.Path(tempfile.mkdtemp())
    try:
        files = _build(root, corpus)
        checked = 0
        for name, blob in files.items():
            if name.endswith((".html", ".xml")):
                assert today.encode() not in blob, f"{name} contains today's date"
                checked += 1
        assert checked >= 10
    finally:
        shutil.rmtree(root)
