"""The registry's own laws.

Each test is named for the rule it defends. Every loop carries an
`assert checked >= N`: a loop over a collection that turns out to be empty
passes by checking nothing, and several tests in a sibling project shipped
green for exactly that reason.
"""

import pathlib
import re

import pytest

from sitegen import spec

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "sitegen"


def test_nav_keys_are_unique_and_resolve():
    keys = [k for k, _, _, _ in spec.NAV]
    assert len(keys) == len(set(keys)), f"duplicate nav keys: {keys}"
    checked = 0
    for key, label, kind, target in spec.NAV:
        assert kind in ("internal", "external"), f"{key}: bad nav kind {kind!r}"
        assert label.strip(), f"{key}: empty label"
        if kind == "internal":
            assert target in spec.KIND_PATHS, (
                f"nav entry {key!r} points at {target!r}, which is not a page kind")
        else:
            assert target.startswith("/"), f"{key}: external target must be a path"
        checked += 1
    assert checked >= 4, f"only checked {checked} nav entries"


def test_a_page_is_authored_or_generated_and_never_both():
    """Prose and figures sharing one key is what made the magazine renderer
    unmaintainable in the sibling project: regeneration clobbered edited
    sentences and nothing could say which half of a page was safe to rewrite."""
    assert not (spec.AUTHORED_KINDS & spec.GENERATED_KINDS)
    assert spec.AUTHORED_KINDS and spec.GENERATED_KINDS
    checked = 0
    for kind, path, source in spec.PAGE_KINDS:
        assert source in ("authored", "generated"), f"{kind}: bad source {source!r}"
        checked += 1
    assert checked == len(spec.PAGE_KINDS) >= 10


def test_page_kinds_have_unique_kinds_and_paths():
    kinds = [k for k, _, _ in spec.PAGE_KINDS]
    paths = [p for _, p, _ in spec.PAGE_KINDS]
    assert len(kinds) == len(set(kinds)), "duplicate page kind"
    assert len(paths) == len(set(paths)), "two page kinds write the same path"
    for path in paths:
        assert not path.startswith("/"), f"{path}: paths are relative to the publish root"


def test_url_for_handles_every_kind():
    sample = {"slug": "a-slug", "category": "culture", "tag": "fractals"}
    checked = 0
    for kind, _, _ in spec.PAGE_KINDS:
        url = spec.url_for(kind, **sample)
        assert url.startswith("/"), f"{kind}: {url!r} is not site-absolute"
        assert "{" not in url, f"{kind}: unsubstituted placeholder in {url!r}"
        assert "//" not in url[1:], f"{kind}: doubled slash in {url!r}"
        checked += 1
    assert checked == len(spec.PAGE_KINDS)


def test_directory_pages_keep_the_trailing_slash_wordpress_served():
    """Existing inbound links and search results point at /<slug>/. Dropping
    the slash silently breaks every one of them."""
    assert spec.url_for("essay", slug="hyperreality-a-primer") == "/hyperreality-a-primer/"
    assert spec.url_for("writing") == "/writing/"
    assert spec.url_for("home") == "/"
    assert spec.url_for("feed") == "/feed.xml"
    assert spec.url_for("notfound") == "/404.html"


def test_url_for_refuses_an_unknown_kind():
    with pytest.raises(KeyError, match="unknown page kind"):
        spec.url_for("newsletter")


def test_mana_map_is_a_reserved_slug():
    """/mana-map/ is served by a DIFFERENT REPOSITORY (macrae/mana-map, as a
    GitHub project site under this user site's custom domain). If this renderer
    ever emits docs/mana-map/index.html the two fight over one URL and one of
    them silently loses — invisible until somebody reports a dead link."""
    assert "mana-map" in spec.RESERVED_SLUGS


def test_every_top_level_output_path_is_a_reserved_slug():
    """Essays live at /<slug>/, so anything else owning a top-level path must
    be refused as a slug or an essay can shadow it."""
    checked = 0
    for kind, path, _ in spec.PAGE_KINDS:
        if kind == "essay":
            continue
        top = path.split("/", 1)[0]
        assert top in spec.RESERVED_SLUGS, (
            f"page kind {kind!r} writes {path!r}, but {top!r} is not in "
            "RESERVED_SLUGS — an essay with that slug would collide with it")
        checked += 1
    assert checked >= 10


def test_closed_vocabularies_are_non_empty_and_consistent():
    assert spec.CATEGORIES and spec.TAGS and spec.STATUSES
    assert len(set(spec.CATEGORIES)) == len(spec.CATEGORIES)
    assert len(set(spec.TAGS)) == len(spec.TAGS)
    checked = 0
    for cat in spec.CATEGORIES:
        assert cat in spec.CATEGORY_LABELS, f"category {cat!r} has no label"
        assert spec.slugify(cat) == cat, f"category {cat!r} is not already a slug"
        checked += 1
    for tag in spec.TAGS:
        assert spec.slugify(tag) == tag, f"tag {tag!r} is not already a slug"
        checked += 1
    assert checked >= len(spec.CATEGORIES) + len(spec.TAGS)
    assert set(spec.CATEGORY_LABELS) == set(spec.CATEGORIES), "label/category drift"


def test_the_copyright_year_is_a_constant_not_a_clock():
    """A computed year is the commonest way a static site loses byte-identical
    rebuild, and it does it at midnight on 1 January when nobody is watching."""
    # Parsed, not grepped. The first version of this test read raw source and
    # failed on spec.py's own comment warning against date.today() -- a check
    # firing on correct data, which is worse than no check at all.
    import ast
    assert isinstance(spec.COPYRIGHT_TO, int)
    checked = 0
    for path in sorted(SRC.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("today", "now", "utcnow"):
                raise AssertionError(
                    f"{path.name}: calls .{node.attr}() -- the build must be "
                    "byte-identical, so no page may read the clock")
        checked += 1
    assert checked >= 1, "no modules scanned"


def test_no_module_builds_a_url_by_hand():
    """url_for is the only URL constructor. A moved page must break the BUILD,
    not the site — a reader cannot resolve a broken link by scrolling."""
    offenders, checked = [], 0
    pattern = re.compile(r'f"/(?:writing|tags|projects|about)[/"]|'
                         r"f'/(?:writing|tags|projects|about)[/']|"
                         r'"/" \+ slug|f"/\{slug\}')
    for path in sorted(SRC.glob("*.py")):
        if path.name == "spec.py":
            continue
        checked += 1
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert checked >= 1, "no renderer modules were scanned — the glob is wrong"
    assert not offenders, "hand-built URLs (use spec.url_for):\n  " + "\n  ".join(offenders)


def test_slugify_is_deterministic_and_ascii():
    cases = {
        "Koch's Snowflake": "kochs-snowflake",
        "Café — Déjà Vu": "cafe-deja-vu",
        "  Multiple   Spaces  ": "multiple-spaces",
        "Data Science": "data-science",
        "COVID-19": "covid-19",
    }
    checked = 0
    for raw, want in cases.items():
        got = spec.slugify(raw)
        assert got == want, f"slugify({raw!r}) == {got!r}, wanted {want!r}"
        assert got == spec.slugify(raw), "slugify is not deterministic"
        checked += 1
    assert checked >= 5
