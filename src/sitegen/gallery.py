"""The gallery: a few hundred images, filtered in the browser.

A STATIC JSON INDEX, NOT THE DATABASE. Filtering happens instantly with no
round trip, it works offline, and there is nothing running to break. D1 stays
the right tool for genuinely large or server-queried data; routing a few
hundred images through an API to justify having built one would make the page
slower and the system bigger for nothing.

THIS IS THE FIRST PAGE ON THE SITE THAT SHIPS JAVASCRIPT, and it earns it:
filters, a lightbox and a slideshow cannot be done without it. It obeys the
same contract an essay would -- the script is local and committed, there is no
inline code anywhere, and the <noscript> path is a real grid of real links to
real per-image pages, not an apology. With JavaScript off you can still browse
every image, read every prompt, and follow every tag.
"""

import json
import re
from pathlib import Path

from . import chrome, facets, spec
from .chrome import esc

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = ROOT / "content" / "gallery" / "index.json"
IMAGES = ROOT / "content" / "gallery" / "images"

# Declared here rather than in front matter, because the gallery is a
# generated page with no front matter of its own. validate.py reads this, so
# the allowlist and the page cannot drift apart.
SCRIPTS = ("gallery.js",)


def load(include_unpublished=False):
    """Published images, or everything when previewing.

    `make preview` threads the same flag the posts use, so an archive of a few
    thousand staged images can be BROWSED in the real gallery -- facets,
    lightbox and all -- which is the only practical way to curate it. It is
    the same renderer with a different filter, never a second code path, and
    the build refuses to write docs/ with the flag set.
    """
    if not INDEX.exists():
        return []
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    images = data.get("images", [])
    if include_unpublished:
        out = [i for i in images if i.get("status") != "archived"]
    else:
        out = [i for i in images if i.get("status") == "published"]
    # NEWEST FIRST. An archive spanning four years is unreadable in filename
    # order, which is what it was sorted by. Undated images sort last rather
    # than being treated as ancient -- absent is not a date.
    out.sort(key=lambda i: (i.get("date") or "0000-00-00", i["file"]), reverse=True)
    return out


PARAMS_RE = re.compile(r"--(\w+)(?:\s+(\S+))?")


def slug_for(image):
    return Path(image["file"]).stem


def series_of(image):
    """The prompt TEXT, parameters stripped -- the thing held constant.

    Re-running a prompt is how this archive was made: the same words, a
    different seed, sometimes a tweaked parameter. So the unit that means
    something is the prompt, not the file. 2,342 images are 404 prompts; 183
    of those are a single four-image grid and the rest are deliberate
    re-runs, the largest explored 52 times.
    """
    text = PARAMS_RE.sub(" ", image.get("prompt") or "")
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()[:120]
    if text:
        return text
    # NO TEXT PROMPT AT ALL. 43 images here were generated from an image
    # prompt alone, so their Description is nothing but parameters. Lumping
    # them under one "untitled" series would collapse 43 unrelated pictures
    # into a single idea, which is the opposite of what this grouping is for.
    # Each becomes its own series, keyed on its job.
    return "job:" + (image.get("job_id") or image.get("id") or "")


def collections(images):
    out = {}
    for i in images:
        if i.get("collection"):
            out.setdefault(i["collection"], []).append(i)
    return dict(sorted(out.items()))


def tags(images):
    out = {}
    for i in images:
        for t in i.get("tags", []):
            out.setdefault(t, []).append(i)
    return dict(sorted(out.items()))


RESERVED_IMAGE_SLUGS = frozenset({"series", "images"})


def series_slug(key):
    """A stable, readable path for a series.

    The hash suffix is not decoration: two prompts can slugify identically
    once punctuation goes, and a collision here would merge two runs into one
    page -- the same class of bug that once merged 542 images onto 135 files.
    """
    import hashlib
    base = spec.slugify(key)[:70].strip("-") or "series"
    return f"{base}-{hashlib.sha1(key.encode()).hexdigest()[:6]}"


def series_groups(images):
    """{key: [images]} newest-first, only runs with more than one take."""
    out = {}
    for i in images:
        out.setdefault(series_of(i), []).append(i)
    return {k: v for k, v in out.items() if len(v) > 1}


def series_index(images):
    """{series key: [slugs]}, newest first within each."""
    out = {}
    for i in images:
        out.setdefault(series_of(i), []).append(slug_for(i))
    return out


def _client_index_with_facets(images, per_image):
    """The smallest thing the filter needs, including each image's facets so
    the browser never has to re-derive them."""
    return [{
        "s": slug_for(i),
        "f": i["file"],
        "a": i.get("title") or "",
        "p": (i.get("prompt") or "")[:400],
        "x": f,
        "r": series_of(i),
        "rs": series_slug(series_of(i)),
    } for i, f in zip(images, per_image)]


def _client_index(images):
    """The smallest thing the filter needs. Kept lean on purpose: this is
    inlined into the page as a data island, and a few hundred rows of prompt
    text is the difference between a fast first paint and a slow one."""
    return [{
        "s": slug_for(i),
        "f": i["file"],
        "t": i["thumb"],
        "w": i["width"],
        "h": i["height"],
        "a": i.get("title") or "",
        "c": i.get("collection") or "",
        "g": i.get("tags", []),
        "p": i.get("prompt", "")[:400],
    } for i in images]


def _tile(image):
    """One tile.

    `data-id` is load-bearing: the curation server identifies an image by it,
    and without it the archive button posted a null id, the server correctly
    answered 404, and the X appeared to do nothing at all. `data-staged` dims
    it in the preview so curating is not guesswork about what is already live.
    """
    s = slug_for(image)
    staged = "" if image.get("status") == "published" else ' data-staged="1"'
    alt = image.get("title") or (image.get("prompt") or "")[:120] or "Untitled"
    return (f'<a class="sm-tile" href="{esc(spec.url_for("image", slug=s))}" '
            f'data-slug="{esc(s)}" data-id="{esc(image["id"])}"{staged}>'
            f'<img src="{esc("/gallery/images/" + image["thumb"])}" '
            f'alt="{esc(alt)}" width="{image["width"]}" height="{image["height"]}" '
            f'loading="lazy" decoding="async">'
            f'</a>')


def render_gallery(corpus, include_unpublished=False):
    images = load(include_unpublished)
    if not images:
        body = ('<h1 class="sm-title">Gallery</h1>'
                '<p class="sm-lede">Nothing published yet.</p>')
        return chrome.page(title="Gallery", body=body, current="gallery",
                           url=spec.url_for("gallery"), wide=True)

    groups, per_image = facets.panel(images)

    # THE PANEL IS RENDERED SERVER-SIDE AS REAL LINKS. Each pill is an <a> to
    # the gallery with a filter in the fragment, so with JavaScript off it is
    # still a readable, linkable index of what the collection contains -- it
    # just does not filter in place. The script upgrades them to buttons.
    def render_group(group):
        pills = "".join(
            f'<li><a class="sm-pill" data-group="{esc(group["key"])}" '
            f'data-value="{esc(value)}" '
            f'href="{esc(spec.url_for("gallery"))}#{esc(group["key"])}={esc(value)}">'
            f'{esc(value)}<span>{count}</span></a></li>'
            for value, count in group["values"])
        return (f'<section class="sm-facet" data-kind="{esc(group["kind"])}">'
                f'<h2>{esc(group["label"])}</h2>'
                f'<ul class="sm-pills sm-facet-pills">{pills}</ul>'
                f'</section>')

    # PRIMARY GROUPS LEAD; THE REST FOLD AWAY. Sixty-four pills is a filing
    # cabinet, not a filter. Theme (clustered from the prompts themselves) and
    # Year answer most questions; everything else is there when wanted.
    # A <details> works with no JavaScript at all, which the rest of the panel
    # already depends on.
    primary = [g for g in groups if g.get("primary")]
    secondary = [g for g in groups if not g.get("primary")]
    panels = [render_group(g) for g in primary]
    if secondary:
        n = sum(len(g["values"]) for g in secondary)
        panels.append(
            f'<details class="sm-more-facets"><summary>More filters '
            f'<span>{n}</span></summary>'
            + "".join(render_group(g) for g in secondary)
            + '</details>')

    data = json.dumps(_client_index_with_facets(images, per_image),
                      separators=(",", ":"))

    body = (
        '<h1 class="sm-title">Gallery</h1>'
        f'<p class="sm-dateline" id="sm-count">{len(images)} images</p>'

        '<div class="sm-gallery-layout">'

        f'<aside class="sm-panel">'
        f'<div class="sm-panel-head">'
        f'<button class="sm-series" type="button" hidden>One per prompt</button>'
        f'<button class="sm-clear" type="button" hidden>Clear filters</button>'
        f'<button class="sm-play" type="button" hidden>Slideshow</button>'
        f'</div>'
        + "".join(panels) +
        f'<noscript><p class="sm-meta">These are links: each one lists what '
        f'the collection holds. Filtering in place, the lightbox and the '
        f'slideshow need JavaScript.</p></noscript>'
        f'</aside>'

        f'<div class="sm-grid" id="sm-grid">'
        + "".join(_tile(i) for i in images)
        + '</div>'
        # Paged, because a wall of two thousand pictures is unreadable before
        # it is slow. Hidden until the script proves it can page.
        f'<div class="sm-more-wrap">'
        f'<button class="sm-more" type="button" hidden>Show more</button>'
        f'</div>'

        '</div>'

        f'<script type="application/json" id="sm-gallery-data">{data}</script>'

        f'<div class="sm-lightbox" id="sm-lightbox" hidden>'
        f'<button class="sm-lb-close" type="button" aria-label="Close">&times;</button>'
        f'<button class="sm-lb-prev" type="button" aria-label="Previous">&#8249;</button>'
        f'<figure class="sm-lb-fig"><img alt=""><figcaption></figcaption></figure>'
        f'<button class="sm-lb-next" type="button" aria-label="Next">&#8250;</button>'
        f'</div>'
    )
    return chrome.page(title="Gallery", body=body, current="gallery",
                       description="Images, mostly made with Midjourney.",
                       url=spec.url_for("gallery"), wide=True,
                       scripts=[{"src": "/assets/" + s} for s in SCRIPTS])


def render_series(corpus, key, images):
    """One prompt, every take of it, laid out together."""
    first = images[0]
    prompt = first.get("prompt") or key
    dates = sorted({i.get("date") for i in images if i.get("date")})
    jobs = len({i.get("job_id") for i in images if i.get("job_id")})
    param_sets = sorted({
        " ".join(f"--{k} {v}" if v is not True else f"--{k}"
                 for k, v in sorted((i.get("parameters") or {}).items()))
        for i in images})
    param_sets = [p for p in param_sets if p]

    meta = [f"{len(images)} takes"]
    if jobs > 1:
        meta.append(f"{jobs} separate runs")
    if dates:
        meta.append(dates[0] if dates[0] == dates[-1] else f"{dates[0]} \u2013 {dates[-1]}")

    varied = ""
    if len(param_sets) > 1:
        rows = "".join(f"<li><code>{esc(p)}</code></li>" for p in param_sets)
        varied = (f'<h2 class="sm-section-head">Parameters that varied</h2>'
                  f'<ul class="sm-param-list">{rows}</ul>')
    elif param_sets:
        varied = (f'<p class="sm-meta">Every take: <code>'
                  f'{esc(param_sets[0])}</code></p>')

    tiles = "".join(
        f'<a class="sm-tile" href="{esc(spec.url_for("image", slug=slug_for(i)))}">'
        f'<img src="{esc("/gallery/images/" + i["thumb"])}" '
        f'alt="{esc((i.get("title") or prompt)[:110])}" '
        f'width="{i["width"]}" height="{i["height"]}" loading="lazy" '
        f'decoding="async"></a>'
        for i in images)

    body = (f'<h1 class="sm-title" style="font-size:1.7rem">'
            f'{esc((first.get("title") or prompt)[:90])}</h1>'
            f'<p class="sm-dateline">{" &middot; ".join(esc(m) for m in meta)} '
            f'&middot; <a href="{esc(spec.url_for("gallery"))}">all images</a></p>'
            f'<p class="sm-prompt">{esc(prompt)}</p>'
            + varied
            + f'<h2 class="sm-section-head">Every take</h2>'
            + f'<div class="sm-grid">{tiles}</div>')
    return chrome.page(title=(first.get("title") or prompt)[:70],
                       body=body, current="gallery", wide=True,
                       description=f"{len(images)} takes of one prompt.",
                       url=spec.url_for("series", slug=series_slug(key)),
                       image="/gallery/images/" + first["file"])


def render_image(corpus, image, neighbours):
    s = slug_for(image)
    prev_img, next_img = neighbours
    title = image.get("title") or (image.get("prompt", "") or "Untitled")[:70]
    params = image.get("parameters") or {}

    nav = []
    if image.get("_series"):
        key, n = image["_series"]
        nav.append(f'<a href="{esc(spec.url_for("series", slug=series_slug(key)))}">'
                   f'1 of {n} takes &rarr;</a>')
    if prev_img:
        nav.append(f'<a href="{esc(spec.url_for("image", slug=slug_for(prev_img)))}">'
                   f'&larr; previous</a>')
    nav.append(f'<a href="{esc(spec.url_for("gallery"))}">all images</a>')
    if next_img:
        nav.append(f'<a href="{esc(spec.url_for("image", slug=slug_for(next_img)))}">'
                   f'next &rarr;</a>')

    meta = []
    if image.get("collection"):
        meta.append(f'<a href="{esc(spec.url_for("gallery"))}#c:{esc(image["collection"])}">'
                    f'{esc(image["collection"])}</a>')
    meta += [f'{image["width"]}&times;{image["height"]}']
    for k, v in sorted(params.items()):
        meta.append(f'--{esc(k)} {esc(v) if v is not True else ""}'.strip())

    pills = "".join(
        f'<li><a href="{esc(spec.url_for("gallery"))}#g:{esc(t)}">{esc(t)}</a></li>'
        for t in image.get("tags", []))

    body = (
        f'<article class="sm-prose">'
        f'<figure class="sm-image-full">'
        f'<img src="{esc("/gallery/images/" + image["file"])}" '
        f'alt="{esc(image.get("title") or image.get("prompt", "")[:120])}" '
        f'width="{image["width"]}" height="{image["height"]}">'
        + (f'<figcaption>{esc(image["caption"])}</figcaption>'
           if image.get("caption") else "")
        + '</figure>'
        f'<p class="sm-dateline">{" &middot; ".join(meta)}</p>'
        + (f'<h1 class="sm-title" style="font-size:1.5rem">{esc(image["title"])}</h1>'
           if image.get("title") else "")
        + (f'<p class="sm-prompt">{esc(image["prompt"])}</p>'
           if image.get("prompt") else "")
        + (f'<ul class="sm-pills">{pills}</ul>' if pills else "")
        + f'<p class="sm-dateline">{" &middot; ".join(nav)}</p>'
        + '</article>')

    return chrome.page(title=title, body=body, current="gallery",
                       description=(image.get("prompt") or "")[:160],
                       url=spec.url_for("image", slug=s), kind="article",
                       image="/gallery/images/" + image["file"])
