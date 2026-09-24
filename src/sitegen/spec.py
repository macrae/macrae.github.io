"""The registry, and nothing else.

Every vocabulary this site has is closed and lives here: what pages exist, what
they are called, where they are written, which are authored and which are
generated. Nothing in this module does work — it is looked up, never called for
an effect.

TWO RULES THIS FILE EXISTS TO ENFORCE:

A PAGE IS AUTHORED OR GENERATED AND NEVER BOTH. Prose and figures sharing one
key is what made an earlier renderer in a sibling project unmaintainable: a
regeneration would clobber an edited sentence, and there was no way to tell
which half of a page was safe to rewrite. The escape hatch is a FRAGMENT — a
generated page may embed a named file from content/fragments/, which has its
own key and its own file, so the two never overwrite each other.

`url_for` IS THE ONLY PLACE A URL IS CONSTRUCTED. A reader cannot resolve a
broken link by scrolling, so a moved page must break the BUILD, not the site.
tests/test_spec.py greps the renderer modules for hand-built paths and fails on
them.
"""

SITE_URL = "https://seanmacrae.com"
AUTHOR = "Sean MacRae"
TITLE = "Sean MacRae"
TAGLINE = "Data science, mathematics, and things I have been thinking about."

# NOT date.today().year. A computed year is the commonest way a static site
# silently loses byte-identical rebuild, and it does it at midnight on 1 January
# when nobody is looking at the diff gate.
COPYRIGHT_FROM = 2020
COPYRIGHT_TO = 2026

FEED_LIMIT = 20
MEASURE = "46rem"

# ---------------------------------------------------------------- navigation

# Order is position. `appendix` renders after a divider in a quieter weight.
# `external` is a DEPARTURE — it leaves this repo entirely, and is styled to
# say so rather than pretending to be internal navigation.
NAV = (
    ("writing",  "Writing",  "internal", "writing"),
    ("projects", "Projects", "internal", "projects"),
    ("gallery",  "Gallery",  "internal", "gallery"),
    ("about",    "About",    "internal", "about"),
    ("mana-map", "Mana Map", "external", "/mana-map/"),
)

# ---------------------------------------------------------------- page kinds

# (kind, output path template, source)
#   "authored"  — a human wrote the words; the build must never rewrite them
#   "generated" — derived from the corpus; safe to regenerate on every build
PAGE_KINDS = (
    ("home",       "index.html",                       "generated"),
    ("essay",      "{slug}/index.html",                "authored"),
    ("writing",    "writing/index.html",               "generated"),
    ("category",   "writing/{category}/index.html",    "generated"),
    ("tag",        "tags/{tag}/index.html",            "generated"),
    ("projects",   "projects/index.html",              "generated"),
    # The gallery is GENERATED from content/gallery/index.json, which is
    # itself half authored: the ingest tool fills in facts (dimensions,
    # prompt, job id) and never touches the curated half (status, title,
    # tags, collection). Same split as everywhere else, one file rather than
    # two, because an image's facts and its curation are one row.
    ("gallery",    "gallery/index.html",               "generated"),
    ("image",      "gallery/{slug}/index.html",        "generated"),
    # A SERIES IS THE ARTIFACT. This archive was made by re-running one
    # prompt to see what the model does differently, so the interesting
    # object is often the whole run rather than any frame of it.
    ("series",     "gallery/series/{slug}/index.html", "generated"),
    ("project",    "projects/{slug}/index.html",       "authored"),
    ("about",      "about/index.html",                 "authored"),
    ("notfound",   "404.html",                         "generated"),
    ("feed",       "feed.xml",                         "generated"),
    ("sitemap",    "sitemap.xml",                      "generated"),
    ("robots",     "robots.txt",                       "generated"),
    ("stylesheet", "site.css",                         "generated"),
)

KIND_PATHS = {k: p for k, p, _ in PAGE_KINDS}
KIND_SOURCE = {k: s for k, _, s in PAGE_KINDS}
AUTHORED_KINDS = frozenset(k for k, _, s in PAGE_KINDS if s == "authored")
GENERATED_KINDS = frozenset(k for k, _, s in PAGE_KINDS if s == "generated")

# Files the build writes but must never prune, because nothing generates them
# on a normal pass and deleting them takes the site down.
PINNED = ("CNAME", ".nojekyll")

CNAME = "seanmacrae.com"

# THE CUTOVER SWITCH, and it is a switch rather than a chore for one reason:
# committing a CNAME file is what TELLS GitHub the custom domain is live, and
# from that moment https://macrae.github.io/ stops serving this site and
# redirects to https://seanmacrae.com/ instead. While DNS still points at
# Bluehost that redirect lands on the old WordPress site, so shipping the
# CNAME early does not just fail to help -- it takes the preview down.
#
# Flip this to True as step 2 of the cutover, AFTER the DNS records point at
# GitHub Pages, and commit the CNAME file that appears.
CUSTOM_DOMAIN_LIVE = False

# ------------------------------------------------------- closed vocabularies

# PROVISIONAL until curation (plan Phase 3). The WordPress taxonomy is not
# carried over: 10 categories for 12 posts, of which one held 7 and every other
# held 1 or 0, and 27 tags of which 16 were used exactly once. A taxonomy where
# almost every term has one member classifies nothing. The original terms ride
# along in each post's front matter as `wp_categories` / `wp_tags` — raw
# material for this decision, never the decision itself.
CATEGORIES = (
    "data-science",
    "machine-learning",
    "mathematics",
    "culture",
    "practice",
)

CATEGORY_LABELS = {
    "data-science":     "Data Science",
    "machine-learning": "Machine Learning",
    "mathematics":      "Mathematics",
    "culture":          "Culture",
    "practice":         "Practice",
}

TAGS = (
    "comics", "covid-19", "evaluation", "fast-ai", "fractals", "generative",
    "hyperreality", "image-restoration", "latent-space", "model-performance",
    "place", "proof", "satire", "scraping", "teams", "time-series",
)

STATUSES = ("published", "staged", "archived")

# ------------------------------------------------------------ reserved slugs

# Essays live at top-level /<slug>/, so anything else that occupies a top-level
# path must be refused as a slug.
#
# `mana-map` IS THE LOAD-BEARING ENTRY. That path is served by a DIFFERENT
# REPOSITORY — GitHub serves macrae/mana-map at <custom-domain>/mana-map/
# because this is the user site and that is a project site. If this renderer
# ever emits docs/mana-map/index.html the two fight over one URL and one of
# them silently loses, which stays invisible until somebody reports a dead
# link. Every future repo that gets Pages enabled joins this tuple.
RESERVED_SLUGS = frozenset({
    "mana-map",          # macrae/mana-map — another repo entirely
    "writing", "tags", "projects", "gallery", "about", "assets", "index", "404",
    "index.html", "404.html",
    "feed.xml", "sitemap.xml", "robots.txt", "site.css", "CNAME", ".nojekyll",
})


def slugify(text):
    """Lowercase, hyphen-separated, ASCII. Used for tags and heading anchors."""
    import re
    import unicodedata
    text = unicodedata.normalize("NFKD", str(text))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    # Apostrophes VANISH rather than separating: WordPress slugified
    # "Koch's Snowflake" to kochs-snowflake, and that permalink is one we
    # have to reproduce byte-for-byte or an inbound link breaks.
    text = text.replace("'", "").replace("\u2019", "")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def path_for(kind, **kw):
    """The output path under the publish root, e.g. 'writing/index.html'."""
    if kind not in KIND_PATHS:
        raise KeyError(
            f"unknown page kind {kind!r}. Add it to PAGE_KINDS — this registry "
            "is the only authority on what pages exist.")
    template = KIND_PATHS[kind]
    try:
        return template.format(**kw)
    except KeyError as exc:
        raise KeyError(f"page kind {kind!r} needs {exc} to build its path") from exc


def url_for(kind, **kw):
    """The site-absolute URL for a page. THE ONLY URL CONSTRUCTOR.

    Directory-index pages return a trailing-slash URL ('/writing/'), which is
    what WordPress served and therefore what every existing inbound link and
    search result expects. Root files return their own name ('/feed.xml').
    """
    path = path_for(kind, **kw)
    if path.endswith("/index.html"):
        return "/" + path[: -len("index.html")]
    if path == "index.html":
        return "/"
    return "/" + path


def absolute(url):
    """Site-absolute path -> fully-qualified URL. For the feed and OpenGraph."""
    if url.startswith(("http://", "https://")):
        return url
    return SITE_URL.rstrip("/") + url
