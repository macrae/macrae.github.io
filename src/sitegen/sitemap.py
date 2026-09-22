"""sitemap.xml and robots.txt.

No <lastmod> unless the entry declares `updated`. An invented lastmod is a
claim about a date nobody recorded — absent means absent.
"""

from . import spec
from .chrome import esc


def render_sitemap(corpus):
    urls = [spec.url_for("home"), spec.url_for("writing"),
            spec.url_for("projects"), spec.url_for("about")]
    urls += [spec.url_for("category", category=c) for c in corpus.by_category()]
    urls += [spec.url_for("tag", tag=t) for t in corpus.by_tag()]
    rows = []
    for u in urls:
        rows.append(f"<url><loc>{esc(spec.absolute(u))}</loc></url>")
    for e in corpus.all_entries:
        if e.meta.get("noindex"):
            continue
        mod = e.meta.get("updated")
        lastmod = f"<lastmod>{esc(mod)}</lastmod>" if mod else ""
        rows.append(f"<url><loc>{esc(spec.absolute(e.url))}</loc>{lastmod}</url>")
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(rows) + "\n</urlset>\n")


def render_robots(corpus):
    return ("User-agent: *\n"
            "Allow: /\n\n"
            f"Sitemap: {spec.absolute(spec.url_for('sitemap'))}\n")
