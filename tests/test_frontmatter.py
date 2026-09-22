"""The parser's refusals, and why it is not PyYAML."""

import pytest

from sitegen import content, frontmatter

HEAD = "---\ntitle: T\nslug: s\ndate: 2020-01-01\nstatus: staged\n"


def parse(extra="", head=HEAD):
    return frontmatter.parse(head + extra + "---\n\nbody\n", "t")


def test_yaml_coercions_that_would_break_determinism_do_not_happen():
    """PyYAML turns `no` into False, `2019-03-04` into a date object and
    `1.10` into 1.1. Each is a way for the content layer to decide what a
    string means, in a build whose whole claim is that content determines
    bytes."""
    meta, _ = parse("wp_id: 1.10\nwp_excerpt: no\ncaptured: 2019-03-04\n")
    assert meta["wp_id"] == "1.10", "a version-like string became a float"
    assert meta["wp_excerpt"] == "no", "`no` became a boolean"
    assert meta["captured"] == "2019-03-04" and isinstance(meta["captured"], str)


def test_an_unknown_key_is_an_error_not_a_warning():
    with pytest.raises(frontmatter.FrontMatterError, match="unknown front-matter key"):
        parse("tittle: typo\n")


def test_status_has_no_default():
    """Publishing-by-omission and archiving-by-omission are both wrong."""
    with pytest.raises(frontmatter.FrontMatterError, match="no `status`"):
        frontmatter.parse("---\ntitle: T\nslug: s\ndate: 2020-01-01\n---\n", "t")


def test_curation_keys_are_required_only_to_publish():
    parse()                                     # staged, no category: fine
    with pytest.raises(frontmatter.FrontMatterError, match="required to publish"):
        parse(head="---\ntitle: T\nslug: s\ndate: 2020-01-01\nstatus: published\n")


def test_a_closed_vocabulary_refuses_an_invented_term():
    head = ("---\ntitle: T\nslug: s\ndate: 2020-01-01\nstatus: published\n"
            "summary: S\ntags: []\n")
    with pytest.raises(frontmatter.FrontMatterError, match="closed vocabulary"):
        parse("category: astrology\n", head=head)


def test_scripts_without_a_fallback_are_refused_at_build_time():
    with pytest.raises(frontmatter.FrontMatterError, match="no `fallback`"):
        parse("scripts:\n  - src: js/x.js\n")


def test_a_remote_script_is_refused():
    with pytest.raises(frontmatter.FrontMatterError, match="remote"):
        parse("fallback: f.png\nscripts:\n  - src: https://cdn.example.com/d3.js\n")


def test_a_bool_must_be_literally_true_or_false():
    with pytest.raises(frontmatter.FrontMatterError, match="literally true or false"):
        parse("feed: yes\n")
    assert parse("feed: false\n")[0]["feed"] is False


def test_the_error_always_names_the_file():
    with pytest.raises(frontmatter.FrontMatterError, match="some/post.md"):
        frontmatter.parse("no fence here", "some/post.md")


def test_every_real_post_round_trips(corpus):
    checked = 0
    for entry in corpus.all_entries:
        assert entry.meta["slug"] == entry.directory.name
        assert entry.meta["date"].count("-") == 2
        assert entry.meta["status"] in ("published", "staged", "archived")
        checked += 1
    assert checked >= 12, f"only {checked} entries parsed — expected 12 migrated posts"
