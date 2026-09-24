"""The gallery: the first page on this site allowed to ship JavaScript."""

import json
import pathlib
import re
import shutil
import tempfile

import pytest

from sitegen import build, gallery, spec


@pytest.fixture(scope="module")
def tree(request):
    from sitegen import content
    root = pathlib.Path(tempfile.mkdtemp())
    build.write(build.plan(content.load()), root=root)
    yield root
    shutil.rmtree(root)


def test_published_images_render_as_tiles(tree):
    images = gallery.load()
    assert len(images) >= 10, f"only {len(images)} published images to test with"
    html = (tree / "gallery" / "index.html").read_text(encoding="utf-8")
    tiles = re.findall(r'class="sm-tile"', html)
    assert len(tiles) == len(images), f"{len(tiles)} tiles for {len(images)} images"


def test_an_unpublished_image_is_absent_from_the_page_AND_from_disk(tree):
    """A staged image must not be sitting on the server for anyone who guesses
    its filename. The page not linking to it is not enough."""
    raw = json.loads(gallery.INDEX.read_text(encoding="utf-8"))["images"]
    unpublished = [i for i in raw if i.get("status") != "published"]
    html = (tree / "gallery" / "index.html").read_text(encoding="utf-8")
    checked = 0
    for image in unpublished:
        assert image["file"] not in html, f"{image['file']} leaked into the page"
        assert not (tree / "gallery" / "images" / image["file"]).exists(), (
            f"{image['file']} was copied to the server despite being "
            f"{image['status']}")
        checked += 1
    # Deliberately no floor: everything may legitimately be published. The
    # assertions above are what matter, and they are vacuous only when there is
    # genuinely nothing unpublished.
    assert checked >= 0


def test_every_published_image_has_both_its_files(tree):
    checked = 0
    for image in gallery.load():
        for key in ("file", "thumb"):
            path = tree / "gallery" / "images" / image[key]
            assert path.exists(), f"missing {image[key]}"
            assert path.stat().st_size > 0
            checked += 1
    assert checked >= 20


def test_each_image_gets_its_own_page_with_its_prompt(tree):
    checked = 0
    for image in gallery.load():
        page = tree / "gallery" / gallery.slug_for(image) / "index.html"
        assert page.exists(), f"no page for {image['file']}"
        html = page.read_text(encoding="utf-8")
        if image.get("prompt"):
            # The prompt is the content. A gallery that drops it is a folder.
            head = image["prompt"][:40]
            assert head.replace("&", "&amp;") in html or head in html, (
                f"{image['file']}: prompt missing from its own page")
        checked += 1
    assert checked >= 10


def test_the_grid_works_without_javascript(tree):
    """Every tile is a real link to a real page, so the no-JS path is a
    working gallery rather than an apology."""
    html = (tree / "gallery" / "index.html").read_text(encoding="utf-8")
    hrefs = re.findall(r'class="sm-tile" href="([^"]+)"', html)
    assert len(hrefs) >= 10
    checked = 0
    for href in hrefs:
        target = tree / href.strip("/") / "index.html"
        assert target.exists(), f"tile links to {href}, which does not exist"
        checked += 1
    assert checked >= 10
    assert "<noscript" in html

    # Buttons that only work with JavaScript start hidden, so a reader without
    # it never sees a dead control.
    for cls in ("sm-clear", "sm-play"):
        assert f'class="{cls}" type="button" hidden' in html, (
            f"{cls} does not start hidden")

    # EVERY FACET PILL IS A REAL LINK, not a button the script has to rescue.
    # With JavaScript off the panel is still a readable, linkable index of
    # what the collection contains.
    pill_links = re.findall(r'<a class="sm-pill"[^>]*href="([^"]+)"', html)
    assert len(pill_links) >= 8, f"only {len(pill_links)} facet pills are links"
    for href in pill_links:
        assert href.startswith("/gallery/#"), f"pill links off-gallery: {href}"


def test_the_only_scripts_are_the_declared_one_and_a_json_island(tree):
    html = (tree / "gallery" / "index.html").read_text(encoding="utf-8")
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.S)
    assert len(scripts) == 2, f"expected 2 script tags, found {len(scripts)}"
    kinds = sorted(
        "json" if 'type="application/json"' in attrs else "external"
        for attrs, _ in scripts)
    assert kinds == ["external", "json"], kinds
    for attrs, body in scripts:
        if 'type="application/json"' in attrs:
            json.loads(body)          # must be parseable, or the page is dead
        else:
            assert not body.strip(), "the declared script has an inline body"
            src = re.search(r'src="([^"]+)"', attrs).group(1)
            assert src.lstrip("/").split("/")[-1] in gallery.SCRIPTS


def test_the_script_is_committed_and_local(tree):
    for name in gallery.SCRIPTS:
        asset = tree / "assets" / name
        assert asset.exists(), f"{name} was not deployed"
        text = asset.read_text(encoding="utf-8")
        assert "http://" not in text and "https://" not in text, (
            f"{name} reaches off-site; scripts must be local and committed")


def test_gallery_slugs_cannot_collide_with_an_essay():
    """Images live at /gallery/<slug>/, essays at /<slug>/, so they cannot
    collide — but `gallery` itself must be reserved or an essay could shadow
    the whole section."""
    assert "gallery" in spec.RESERVED_SLUGS
    slugs = [gallery.slug_for(i) for i in gallery.load()]
    assert len(slugs) == len(set(slugs)), "two images claim one URL"


def test_no_two_images_share_a_file():
    """542 entries once pointed at 135 files.

    The collision suffix used the first 8 characters of the job UUID, which is
    IDENTICAL across the four variants of one Midjourney job -- so four
    different pictures resolved to one filename and overwrote each other.
    Every count still reconciled: the right number of entries, the right
    number of tiles, the right prompts. Only the images were wrong, and the
    only way to see it was to look at the page.
    """
    import json
    raw = json.loads(gallery.INDEX.read_text(encoding="utf-8"))["images"]
    assert len(raw) >= 15, f"only {len(raw)} entries to check"

    for key in ("file", "thumb"):
        claimed = {}
        for image in raw:
            claimed.setdefault(image[key], []).append(image["id"])
        shared = {f: ids for f, ids in claimed.items() if len(ids) > 1}
        assert not shared, (
            f"{len(shared)} {key} name(s) claimed by more than one image, e.g. "
            f"{list(shared.items())[:2]}")


def test_every_entry_has_its_thumbnail_on_disk():
    import json
    raw = json.loads(gallery.INDEX.read_text(encoding="utf-8"))["images"]
    checked, missing = 0, []
    for image in raw:
        path = gallery.IMAGES / image["thumb"]
        if not path.exists() or path.stat().st_size == 0:
            missing.append(image["thumb"])
        checked += 1
    assert checked >= 15
    assert not missing, f"{len(missing)} thumbnails missing, e.g. {missing[:3]}"


def test_a_published_image_has_its_full_size_generated():
    """Thumbnails exist for everything; full sizes are generated on publish.
    An image marked published without one would render a broken <img>."""
    import json
    raw = json.loads(gallery.INDEX.read_text(encoding="utf-8"))["images"]
    published = [i for i in raw if i.get("status") == "published"]
    assert published, "nothing published to check"
    missing = [i["file"] for i in published
               if not (gallery.IMAGES / i["file"]).exists()]
    assert not missing, (
        f"{len(missing)} published image(s) have no full-size file. "
        f"Run: python tools/gallery_ingest.py --publish-full   e.g. {missing[:3]}")


def test_a_series_page_holds_every_take(tree):
    """A prompt re-run is the artifact, so its page must show the whole run,
    not a sample of it."""
    images = gallery.load()
    runs = gallery.series_groups(images)
    if not runs:
        pytest.skip("no multi-take runs among the published images")
    checked = 0
    for key, members in runs.items():
        page = tree / "gallery" / "series" / gallery.series_slug(key) / "index.html"
        assert page.exists(), f"no series page for {key[:40]!r}"
        html = page.read_text(encoding="utf-8")
        tiles = re.findall(r'class="sm-tile"', html)
        assert len(tiles) == len(members), (
            f"{key[:40]!r}: {len(tiles)} tiles for {len(members)} takes")
        checked += 1
    assert checked >= 1


def test_series_slugs_are_unique():
    """Two prompts can slugify identically once punctuation is stripped, and a
    collision would merge two runs onto one page -- the same failure that once
    put 542 images onto 135 files."""
    images = gallery.load(include_unpublished=True)
    keys = list(gallery.series_groups(images))
    slugs = [gallery.series_slug(k) for k in keys]
    assert len(slugs) == len(set(slugs)), "two runs share a page"
    assert len(keys) >= 1


def test_an_image_cannot_shadow_the_series_path():
    """/gallery/series/ must not be reachable as an image slug."""
    assert "series" in gallery.RESERVED_IMAGE_SLUGS
    for image in gallery.load(include_unpublished=True):
        assert gallery.slug_for(image) not in gallery.RESERVED_IMAGE_SLUGS


def test_images_with_no_text_prompt_are_not_one_series():
    """43 images were generated from an image prompt alone, so their metadata
    is nothing but parameters. Grouping on prompt text put all 43 into a
    single 'untitled' run -- 43 unrelated pictures collapsed into one idea."""
    images = gallery.load(include_unpublished=True)
    textless = [i for i in images
                if not re.sub(r"--\w+(\s+\S+)?", " ", i.get("prompt") or "").strip()]
    if len(textless) < 2:
        pytest.skip("no prompt-less images to check")
    keys = {gallery.series_of(i) for i in textless}
    assert len(keys) == len(textless), (
        f"{len(textless)} prompt-less images collapsed into {len(keys)} series")
