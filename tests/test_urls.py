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


def test_no_entry_claims_a_reserved_path(corpus):
    checked = 0
    for entry in corpus.all_entries:
        assert entry.slug not in spec.RESERVED_SLUGS, f"{entry.slug} is reserved"
        checked += 1
    assert checked >= 12


def test_mana_map_is_never_emitted_by_this_renderer(corpus):
    """That path belongs to macrae/mana-map, a different repository served at
    the same domain. Two writers of one URL means one of them loses
    silently."""
    from sitegen import build
    pages = build.plan(corpus)
    for path in pages:
        assert not path.startswith("mana-map/"), (
            f"this renderer emitted {path}, colliding with the other repository")
