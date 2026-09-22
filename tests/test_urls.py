"""The migration safety net: nobody's bookmarks break."""

from sitegen import spec


def test_every_migrated_post_keeps_its_wordpress_permalink(corpus):
    """WordPress served /<slug>/ with no date hierarchy, which a static site
    reproduces exactly as <slug>/index.html. This asserts we actually did,
    for every post that carries a recorded original URL."""
    checked = 0
    for entry in corpus.essays:
        original = entry.meta.get("wp_link")
        if not original:
            continue
        expected = spec.absolute(spec.url_for("essay", slug=entry.slug))
        assert original.rstrip("/") + "/" == expected, (
            f"{entry.slug}: was served at {original}, would now be at "
            f"{expected} — an inbound link would break")
        checked += 1
    assert checked >= 12, f"only {checked} posts carry a wp_link"


def test_no_ESSAY_claims_a_reserved_path(corpus):
    """Scoped to essays on purpose. RESERVED_SLUGS protects the TOP-LEVEL
    namespace, because essays live at /<slug>/. A project lives at
    /projects/<slug>/ and cannot collide with it -- which is why there is a
    project legitimately called mana-map sitting at /projects/mana-map/ while
    /mana-map/ belongs to another repository entirely.

    The first version of this test asserted over every entry and failed on
    exactly that project: a check firing on correct data."""
    checked = 0
    for entry in corpus.essays:
        assert entry.slug not in spec.RESERVED_SLUGS, f"{entry.slug} is reserved"
        checked += 1
    assert checked >= 12

    for entry in corpus.projects:
        path = spec.path_for("project", slug=entry.slug)
        assert path.startswith("projects/"), f"{entry.slug} escaped /projects/"


def test_mana_map_is_never_emitted_by_this_renderer(corpus):
    """That path belongs to macrae/mana-map, a different repository served at
    the same domain. Two writers of one URL means one of them loses
    silently."""
    from sitegen import build
    pages = build.plan(corpus)
    for path in pages:
        assert not path.startswith("mana-map/"), (
            f"this renderer emitted {path}, colliding with the other repository")
