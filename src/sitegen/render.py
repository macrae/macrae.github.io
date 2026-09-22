"""One function per page kind, each returning a string.

build.py iterates spec.PAGE_KINDS and dispatches here, so adding a page means
adding a registry row and a function — and forgetting the function is a
KeyError at build time rather than a page that quietly never appears.

GENERATED pages that need human words take them from a FRAGMENT
(content/fragments/<name>.md). The fragment is its own file with its own key,
so regenerating a list can never overwrite an edited sentence. That is the
whole of the authored/generated escape hatch.
"""

from . import chrome, content, markdown, spec
from .chrome import esc

MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")


def human_date(iso):
    """'2020-04-15' -> '15 April 2020'. Pure string work; never reads a clock."""
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]} {y}"


def month_year(iso):
    y, m, _ = iso.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"


def _body_html(entry, check_internal=None):
    """An entry's markdown, with its own directory as the asset root."""
    html_out, _ = markdown.render(
        entry.body,
        where=str(entry.directory / "index.md"),
        ns=entry.slug,
        resolve=lambda rel: entry.directory / rel,
        check_internal=check_internal,
    )
    return html_out


def _fragment_html(corpus, name):
    html_out, _ = markdown.render(content.fragment(corpus, name),
                                  where=f"fragments/{name}.md")
    return html_out


def _dateline(entry):
    bits = [f'<time datetime="{esc(entry.date)}">{esc(human_date(entry.date))}</time>']
    if entry.category:
        bits.append(f'<a href="{esc(spec.url_for("category", category=entry.category))}">'
                    f'{esc(spec.CATEGORY_LABELS[entry.category])}</a>')
    if entry.meta.get("updated"):
        bits.append(f"revised {esc(month_year(entry.meta['updated']))}")
    return f'<p class="sm-dateline">{" &middot; ".join(bits)}</p>'


def _tag_pills(entry):
    if not entry.tags:
        return ""
    items = "".join(
        f'<li><a href="{esc(spec.url_for("tag", tag=t))}">{esc(t)}</a></li>'
        for t in entry.tags)
    return f'<ul class="sm-pills">{items}</ul>'


def _noscript_fallback(entry):
    """Every interactive page carries one. The build refuses otherwise."""
    fb = entry.meta.get("fallback")
    if not entry.interactive or not fb:
        return ""
    return (f'<noscript><figure class="sm-fallback">'
            f'<img src="{esc(fb)}" alt="Static view of the interactive figure.">'
            f'<figcaption>This figure is interactive. '
            f'Shown here as a static image.</figcaption>'
            f'</figure></noscript>')


# ------------------------------------------------------------------ entries

def render_essay(corpus, entry, check_internal=None):
    body = (f'<article class="sm-prose">'
            f'<h1 class="sm-title">{esc(entry.title)}</h1>'
            + _dateline(entry)
            + (f'<p class="sm-lede">{esc(entry.meta["summary"])}</p>'
               if entry.meta.get("summary") else "")
            + _noscript_fallback(entry)
            + _body_html(entry, check_internal)
            + _tag_pills(entry)
            + "</article>")
    return chrome.page(
        title=entry.title, body=body, description=entry.meta.get("summary", ""),
        url=entry.url, current="writing", kind="article",
        image=entry.meta.get("hero"), noindex=entry.meta.get("noindex", False),
        styles=entry.meta.get("styles", ()), scripts=entry.meta.get("scripts", ()))


def render_project(corpus, entry, check_internal=None):
    body = (f'<article class="sm-prose">'
            f'<h1 class="sm-title">{esc(entry.title)}</h1>'
            + _dateline(entry)
            + (f'<p class="sm-lede">{esc(entry.meta["summary"])}</p>'
               if entry.meta.get("summary") else "")
            + _body_html(entry, check_internal)
            + _tag_pills(entry)
            + "</article>")
    return chrome.page(
        title=entry.title, body=body, description=entry.meta.get("summary", ""),
        url=entry.url, current="projects", kind="article",
        styles=entry.meta.get("styles", ()), scripts=entry.meta.get("scripts", ()))


# ------------------------------------------------------------------ indexes

def _entry_row(entry):
    meta = [f'<time datetime="{esc(entry.date)}">{esc(month_year(entry.date))}</time>']
    if entry.category:
        meta.append(f'<a href="{esc(spec.url_for("category", category=entry.category))}">'
                    f'{esc(spec.CATEGORY_LABELS[entry.category])}</a>')
    summary = entry.meta.get("summary") or ""
    return (f'<li class="sm-item">'
            f'<h2><a href="{esc(entry.url)}">{esc(entry.title)}</a></h2>'
            f'<p class="sm-meta">{" &middot; ".join(meta)}</p>'
            + (f"<p>{esc(summary)}</p>" if summary else "")
            + "</li>")


def _entry_list(entries):
    if not entries:
        return '<p class="sm-meta">Nothing here yet.</p>'
    return f'<ul class="sm-list">{"".join(_entry_row(e) for e in entries)}</ul>'


def render_home(corpus):
    intro = _fragment_html(corpus, "home") if "home" in corpus.fragments else ""
    recent = corpus.essays[:5]
    body = [f'<div class="sm-prose">{intro}</div>' if intro else ""]
    body.append(f'<h2 class="sm-section-head">Recent writing</h2>')
    body.append(_entry_list(recent))
    if len(corpus.essays) > len(recent):
        body.append(f'<p class="sm-meta" style="margin-top:1rem">'
                    f'<a href="{esc(spec.url_for("writing"))}">All writing '
                    f'&rarr;</a></p>')
    if corpus.projects:
        body.append('<h2 class="sm-section-head">Projects</h2>')
        body.append(_entry_list(corpus.projects[:4]))
    # The hand-off to the other repository, drawn as a departure.
    body.append(
        '<a class="sm-depart-card" href="/mana-map/">'
        '<strong>Mana Map &#8599;</strong>'
        '<span>A workbench for designing and measuring Commander decks: a '
        '34,900-card atlas, a seeded simulator, and every claim carrying the '
        'experiment behind it.</span></a>')
    return chrome.page(title=spec.TITLE, body="".join(body),
                       description=spec.TAGLINE, url=spec.url_for("home"))


def render_writing_index(corpus):
    intro = (f'<div class="sm-prose">{_fragment_html(corpus, "writing")}</div>'
             if "writing" in corpus.fragments else "")
    cats = corpus.by_category()
    pills = "".join(
        f'<li><a href="{esc(spec.url_for("category", category=c))}">'
        f'{esc(spec.CATEGORY_LABELS[c])} ({len(v)})</a></li>'
        for c, v in cats.items())
    body = (f'<h1 class="sm-title">Writing</h1>'
            + intro
            + (f'<ul class="sm-pills">{pills}</ul>' if pills else "")
            + '<h2 class="sm-section-head">All posts</h2>'
            + _entry_list(corpus.essays))
    return chrome.page(title="Writing", body=body, current="writing",
                       description="Essays on data science, mathematics and culture.",
                       url=spec.url_for("writing"))


def render_category_index(corpus, category):
    entries = corpus.by_category().get(category, ())
    label = spec.CATEGORY_LABELS[category]
    body = (f'<h1 class="sm-title">{esc(label)}</h1>'
            f'<p class="sm-dateline">{len(entries)} '
            f'{"post" if len(entries) == 1 else "posts"} &middot; '
            f'<a href="{esc(spec.url_for("writing"))}">all writing</a></p>'
            + _entry_list(entries))
    return chrome.page(title=label, body=body, current="writing",
                       description=f"Posts about {label.lower()}.",
                       url=spec.url_for("category", category=category))


def render_tag_index(corpus, tag):
    entries = corpus.by_tag().get(tag, ())
    body = (f'<h1 class="sm-title">{esc(tag)}</h1>'
            f'<p class="sm-dateline">{len(entries)} '
            f'{"post" if len(entries) == 1 else "posts"} &middot; '
            f'<a href="{esc(spec.url_for("writing"))}">all writing</a></p>'
            + _entry_list(entries))
    return chrome.page(title=f"Tagged {tag}", body=body, current="writing",
                       description=f"Posts tagged {tag}.",
                       url=spec.url_for("tag", tag=tag))


def render_projects(corpus):
    intro = (f'<div class="sm-prose">{_fragment_html(corpus, "projects")}</div>'
             if "projects" in corpus.fragments else "")
    body = (f'<h1 class="sm-title">Projects</h1>' + intro
            + _entry_list(corpus.projects))
    return chrome.page(title="Projects", body=body, current="projects",
                       description="Things built, and what they were for.",
                       url=spec.url_for("projects"))


def render_about(corpus):
    about = next((e for e in corpus.all_entries if e.slug == "about"), None)
    if about is None:
        body = ('<h1 class="sm-title">About</h1>'
                '<p class="sm-meta">Not written yet.</p>')
    else:
        body = (f'<article class="sm-prose"><h1 class="sm-title">'
                f'{esc(about.title)}</h1>{_body_html(about)}</article>')
    return chrome.page(title="About", body=body, current="about",
                       description=f"About {spec.AUTHOR}.",
                       url=spec.url_for("about"))


def render_404(corpus):
    body = ('<h1 class="sm-title">Not found</h1>'
            '<p class="sm-lede">There is nothing at this address.</p>'
            f'<p><a href="{esc(spec.url_for("writing"))}">All writing</a> '
            f'&middot; <a href="{esc(spec.url_for("home"))}">Home</a></p>')
    return chrome.page(title="Not found", body=body, url=spec.url_for("notfound"),
                       noindex=True)
