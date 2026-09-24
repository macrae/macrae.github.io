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

from . import chrome, spec
from .chrome import esc

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = ROOT / "content" / "gallery" / "index.json"
IMAGES = ROOT / "content" / "gallery" / "images"

# Declared here rather than in front matter, because the gallery is a
# generated page with no front matter of its own. validate.py reads this, so
# the allowlist and the page cannot drift apart.
SCRIPTS = ("gallery.js",)


def load():
    if not INDEX.exists():
        return []
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    return [i for i in data.get("images", []) if i.get("status") == "published"]


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
    alt = image.get("title") or image.get("prompt", "")[:120] or "Untitled"
    return (f'<a class="sm-tile" href="{esc(spec.url_for("image", slug=s))}" '
            f'data-slug="{esc(s)}">'
            f'<img src="{esc("/gallery/images/" + image["thumb"])}" '
            f'alt="{esc(alt)}" width="{image["width"]}" height="{image["height"]}" '
            f'loading="lazy" decoding="async">'
            f'</a>')


def render_gallery(corpus):
    images = load()
    if not images:
        body = ('<h1 class="sm-title">Gallery</h1>'
                '<p class="sm-lede">Nothing published yet.</p>')
        return chrome.page(title="Gallery", body=body, current="gallery",
                           url=spec.url_for("gallery"), wide=True)

    cols, tag_map = collections(images), tags(images)
    chips = ['<button class="sm-chip is-on" data-filter="all">All '
             f'<span>{len(images)}</span></button>']
    for name, items in cols.items():
        chips.append(f'<button class="sm-chip" data-filter="c:{esc(name)}">'
                     f'{esc(name)} <span>{len(items)}</span></button>')
    for name, items in tag_map.items():
        chips.append(f'<button class="sm-chip" data-filter="g:{esc(name)}">'
                     f'{esc(name)} <span>{len(items)}</span></button>')

    data = json.dumps(_client_index(images), separators=(",", ":"))

    body = (
        '<h1 class="sm-title">Gallery</h1>'
        f'<p class="sm-dateline">{len(images)} images'
        + (f' &middot; {len(cols)} collections' if cols else "")
        + (f' &middot; {len(tag_map)} tags' if tag_map else "") + '</p>'

        # Controls are hidden until the script proves it is running, so a
        # reader without JavaScript never sees buttons that do nothing.
        f'<div class="sm-controls" hidden>'
        f'<div class="sm-chips">{"".join(chips)}</div>'
        f'<button class="sm-play" type="button">Slideshow</button>'
        f'</div>'

        f'<div class="sm-grid" id="sm-grid">'
        + "".join(_tile(i) for i in images)
        + '</div>'

        # The data island. Not a script: a script tag with a body would fail
        # the site's own validator, and rightly.
        f'<script type="application/json" id="sm-gallery-data">{data}</script>'

        f'<noscript><p class="sm-meta">Filters and the slideshow need '
        f'JavaScript. Every image below still opens on its own page, with its '
        f'prompt.</p></noscript>'

        # The lightbox shell, empty until the script fills it.
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
