"""The shell every page goes through.

One funnel, so that `lang`, the viewport, the canonical URL, the OpenGraph
block, the hashed stylesheet link and the feed's <link rel="alternate"> cannot
be forgotten on one page out of thirty. A page that skips the funnel is a page
where one of those is missing and nobody notices for a year.

NO JSON-LD, DELIBERATELY. Structured data would mean a
<script type="application/ld+json">, and the moment the validator's no-script
rule carries one exception it stops being a rule and becomes a negotiation.
OpenGraph and Twitter cards are plain <meta> tags and get most of the benefit.
"""

import html as _html

from . import design, spec


def esc(text):
    return _html.escape(str(text), quote=True)


def _meta(name, content, prop=False):
    if not content:
        return ""
    key = "property" if prop else "name"
    return f'<meta {key}="{esc(name)}" content="{esc(content)}">'


def head(*, title, description="", url="/", kind="website", image=None,
         noindex=False, styles=(), scripts=()):
    full_title = title if title == spec.TITLE else f"{title} — {spec.TITLE}"
    parts = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{esc(full_title)}</title>",
        _meta("description", description),
        f'<link rel="canonical" href="{esc(spec.absolute(url))}">',
        # The content hash IS the cache-buster; there is no integer to forget.
        f'<link rel="stylesheet" href="{esc(spec.url_for("stylesheet"))}'
        f'?v={design.stylesheet_version()}">',
        f'<link rel="alternate" type="application/atom+xml" '
        f'title="{esc(spec.TITLE)}" href="{esc(spec.url_for("feed"))}">',
        _meta("og:site_name", spec.TITLE, prop=True),
        _meta("og:title", title, prop=True),
        _meta("og:description", description, prop=True),
        _meta("og:type", kind, prop=True),
        _meta("og:url", spec.absolute(url), prop=True),
        _meta("twitter:card", "summary_large_image" if image else "summary"),
    ]
    if image:
        parts.append(_meta("og:image", spec.absolute(image), prop=True))
    if noindex:
        parts.append(_meta("robots", "noindex"))
    for href in styles:
        parts.append(f'<link rel="stylesheet" href="{esc(href)}">')
    for entry in scripts:
        # DEFER IS THE DEFAULT, and opting out is the thing you have to say.
        #
        # Scripts are emitted in <head>, so without `defer` they execute
        # before the document they are about exists. The gallery shipped
        # exactly like that: getElementById returned null, the script's own
        # guard returned early, and nothing filtered, errored or logged. A
        # render-blocking head script is almost never what a content site
        # wants, so the safe behaviour is the one you get for free.
        blocking = str(entry.get("defer", "true")).lower() == "false"
        attr = "" if blocking else " defer"
        parts.append(f'<script src="{esc(entry["src"])}"{attr}></script>')
    return "".join(p for p in parts if p)


def nav(current=None):
    items = []
    for key, label, kind, target in spec.NAV:
        if kind == "internal":
            href = spec.url_for(target)
            cur = ' aria-current="page"' if key == current else ""
            items.append(f'<a href="{esc(href)}"{cur}>{esc(label)}</a>')
        else:
            # A DEPARTURE. /mana-map/ is served by a different repository and
            # is a different visual world; the class and the arrow say you are
            # leaving rather than navigating.
            items.append(f'<a class="sm-depart" href="{esc(target)}">{esc(label)}</a>')
    return (f'<header class="sm-head"><div class="sm-head-inner">'
            f'<a class="sm-wordmark" href="{esc(spec.url_for("home"))}">'
            f'{esc(spec.TITLE)}</a>'
            f'<nav class="sm-nav">{"".join(items)}</nav></div></header>')


def footer():
    years = (f"{spec.COPYRIGHT_FROM}–{spec.COPYRIGHT_TO}"
             if spec.COPYRIGHT_TO != spec.COPYRIGHT_FROM else str(spec.COPYRIGHT_FROM))
    return (f'<footer class="sm-foot"><div class="sm-foot-inner">'
            f'<span>© {years} {esc(spec.AUTHOR)}</span>'
            f'<a href="{esc(spec.url_for("feed"))}">Feed</a>'
            f'<a href="https://github.com/macrae" rel="noopener">GitHub</a>'
            f'<a href="mailto:s.mac925@gmail.com">Email</a>'
            f'</div></footer>')


def page(*, title, body, description="", url="/", current=None, kind="website",
         image=None, noindex=False, wide=False, styles=(), scripts=()):
    # `wide` is False for prose, True for a wide page, or "gallery" for the
    # widest -- a grid of pictures wants the screen, prose does not.
    trim = ("sm-wide sm-gallery-wide" if wide == "gallery"
            else "sm-wide" if wide else "sm-trim")
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>'
        + head(title=title, description=description, url=url, kind=kind,
               image=image, noindex=noindex, styles=styles, scripts=scripts)
        + "</head>\n<body>"
        + nav(current)
        + f'<main class="{trim}">{body}</main>'
        + footer()
        + "</body>\n</html>\n"
    )
