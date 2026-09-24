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
        return [i for i in images if i.get("status") != "archived"]
    return [i for i in images if i.get("status") == "published"]


def slug_for(image):
    return Path(image["file"]).stem


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


def _client_index_with_facets(images, per_image):
    """The smallest thing the filter needs, including each image's facets so
    the browser never has to re-derive them."""
    return [{
        "s": slug_for(i),
        "f": i["file"],
        "a": i.get("title") or "",
        "p": (i.get("prompt") or "")[:400],
        "x": f,
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
    s = slug_for(image)
    staged = ' data-staged="1"' if image.get("status") != "published" else ""
    alt = image.get("title") or image.get("prompt", "")[:120] or "Untitled"
    return (f'<a class="sm-tile" href="{esc(spec.url_for("image", slug=s))}" '
            f'data-slug="{esc(s)}">'
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
    panels = []
    for group in groups:
        pills = "".join(
            f'<li><a class="sm-pill" data-group="{esc(group["key"])}" '
            f'data-value="{esc(value)}" '
            f'href="{esc(spec.url_for("gallery"))}#{esc(group["key"])}={esc(value)}">'
            f'{esc(value)}<span>{count}</span></a></li>'
            for value, count in group["values"])
        panels.append(
            f'<section class="sm-facet" data-kind="{esc(group["kind"])}">'
            f'<h2>{esc(group["label"])}</h2>'
            f'<ul class="sm-pills sm-facet-pills">{pills}</ul>'
            f'</section>')

    data = json.dumps(_client_index_with_facets(images, per_image),
                      separators=(",", ":"))

    body = (
        '<h1 class="sm-title">Gallery</h1>'
        f'<p class="sm-dateline" id="sm-count">{len(images)} images</p>'

        '<div class="sm-gallery-layout">'

        f'<aside class="sm-panel">'
        f'<div class="sm-panel-head">'
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


def render_image(corpus, image, neighbours):
    s = slug_for(image)
    prev_img, next_img = neighbours
    title = image.get("title") or (image.get("prompt", "") or "Untitled")[:70]
    params = image.get("parameters") or {}

    nav = []
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
