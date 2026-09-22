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


def test_nojekyll_survives_pruning(corpus):
    """Without it, Pages runs Jekyll over the tree and silently drops anything
    whose name begins with an underscore."""
    root = pathlib.Path(tempfile.mkdtemp())
    try:
        build.write(build.plan(corpus), root=root)
        assert (root / ".nojekyll").exists()
    finally:
        shutil.rmtree(root)


def test_the_cname_follows_the_cutover_switch(corpus, monkeypatch):
    """The CNAME file IS the thing that makes the custom domain live, so it
    must not appear until DNS has moved -- otherwise macrae.github.io
    redirects to a domain still serving WordPress."""
    from sitegen import spec
    root = pathlib.Path(tempfile.mkdtemp())
    try:
        build.write(build.plan(corpus), root=root)
        assert not (root / "CNAME").exists(), "CNAME shipped before cutover"

        monkeypatch.setattr(spec, "CUSTOM_DOMAIN_LIVE", True)
        build.write(build.plan(corpus), root=root)
        assert (root / "CNAME").read_text().strip() == spec.CNAME
    finally:
        shutil.rmtree(root)


def test_the_page_chrome_carries_no_date_at_all(corpus):
    """A page stamped with 'now' changes on every build and destroys the
    byte-identical rebuild claim.

    SCOPED TO THE CHROME, and the scoping is the point. The first version of
    this test searched whole pages for today's date and failed the moment a
    project page was legitimately dated today -- a check firing on correct
    data, which is worse than no check. An essay may say any date it likes;
    the furniture around it may say none.

    The clock is caught properly in two other places: test_spec asserts via
    the AST that no module calls .today()/.now(), and the two-build
    comparison above catches any nondeterminism whatever its source.
    """
    import re
    root = pathlib.Path(tempfile.mkdtemp())
    try:
        files = _build(root, corpus)
        checked = 0
        for name, blob in files.items():
            if not name.endswith(".html"):
                continue
            html = blob.decode("utf-8")
            head = html[html.index("<head>"):html.index("</head>")]
            foot = html[html.index('<footer'):]
            for region, label in ((head, "head"), (foot, "footer")):
                found = re.search(r"\d{4}-\d{2}-\d{2}", region)
                assert not found, f"{name}: a date in the {label}: {found.group()}"
            checked += 1
        assert checked >= 10, f"only {checked} pages checked"
    finally:
        shutil.rmtree(root)
