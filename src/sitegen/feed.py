"""The Atom feed.

ATOM, NOT RSS, AND NOT BOTH. Atom mandates an explicit stable <id> per entry
and unambiguous RFC-3339 dates; RSS's pubDate is RFC-822 and its guid is
optional, which makes both a determinism hazard. Emitting both would be two
sources of truth for one thing.

<updated> IS THE NEWEST DATE IN THE CORPUS, NEVER THE CLOCK. A feed stamped
`now` changes on every build, which would fail the byte-diff gate on a run
where no content moved at all.
"""

from . import markdown, spec
from .chrome import esc


def _rfc3339(iso_date):
    return f"{iso_date}T00:00:00Z"


def _entry_html(entry):
    """The script-free rendering. A feed reader runs no JavaScript, so an
    interactive figure must arrive as its static fallback or not at all."""
    html_out, _ = markdown.render(
        entry.body, where=str(entry.directory / "index.md"), ns=entry.slug,
        resolve=lambda rel: entry.directory / rel,
        asset_url=lambda rel: spec.absolute(entry.url + rel),
    )
    assert "<script" not in html_out.lower(), (
        f"{entry.slug}: a <script> reached the feed body")
    return html_out


def render_feed(corpus):
    entries = [e for e in corpus.essays if e.meta.get("feed", True)][:spec.FEED_LIMIT]
    out = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f"<title>{esc(spec.TITLE)}</title>",
        f"<subtitle>{esc(spec.TAGLINE)}</subtitle>",
        f'<link href="{esc(spec.absolute(spec.url_for("feed")))}" rel="self"/>',
        f'<link href="{esc(spec.SITE_URL)}/"/>',
        f"<id>{esc(spec.SITE_URL)}/</id>",
        f"<updated>{_rfc3339(corpus.latest_date())}</updated>",
        f"<author><name>{esc(spec.AUTHOR)}</name></author>",
    ]
    for e in entries:
        url = spec.absolute(e.url)
        out += [
            "<entry>",
            f"<title>{esc(e.title)}</title>",
            f'<link href="{esc(url)}"/>',
            f"<id>{esc(url)}</id>",
            f"<published>{_rfc3339(e.date)}</published>",
            f"<updated>{_rfc3339(e.meta.get('updated', e.date))}</updated>",
            f"<summary>{esc(e.meta.get('summary', ''))}</summary>",
            f'<content type="html">{esc(_entry_html(e))}</content>',
        ]
        if e.category:
            out.append(f'<category term="{esc(e.category)}"/>')
        for tag in e.tags:
            out.append(f'<category term="{esc(tag)}"/>')
        out.append("</entry>")
    out.append("</feed>")
    return "\n".join(out) + "\n"
