"""archive/ -> content/posts/<slug>/index.md. Reads the disk, never the network.

A HAND-WRITTEN WALKER OVER A CLOSED TAG VOCABULARY, and the reason is the tag
census: the entire corpus of 12 posts uses exactly 31 distinct HTML tags. That
closed set is the whole argument. A converter with a whitelist RAISES on tag
32; every library silently degrades it.

  - pandoc has no hook for "this <img> is an equation, emit $A_{n}$ from its
    alt" -- which is worth more here than everything pandoc offers -- and it
    emits pandoc-markdown attribute syntax, not the CommonMark this renderer
    parses.
  - html2text is a TEXT renderer: it hard-wraps lines by default, destroying
    per-paragraph diffs forever, and its escaping corrupts <code>.
  - markdownify is the honest runner-up and is rejected for one behaviour:
    unknown tags pass through as their text content. That is precisely how you
    lose a <video> and never find out.

~300 auditable lines is the property that matters when the source is about to
be destroyed.

NOTHING HERE GUESSES. No code language is detected (a wrong ```python on an R
block is a visible lie; 20 blocks across 3 posts is a ten-minute manual pass in
overrides/). No alt text is synthesised (98 images have none, and that is a
separate human job). Every empty paragraph dropped is COUNTED and printed --
231 of them in inverse-modeling-covid-19 -- because a silent drop is the thing
this migration is most afraid of.
"""

import html as _html
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_wp import un_photon                                    # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "archive"
POSTS_OUT = ROOT / "content" / "posts"
OVERRIDES = Path(__file__).resolve().parent / "overrides"

# Measured across all 12 posts, 2026-09-22. Tag 32 raises.
KNOWN_TAGS = {
    "p", "img", "span", "figure", "li", "td", "em", "code", "h2", "strong",
    "hr", "tr", "div", "a", "pre", "ul", "h3", "figcaption", "b", "i", "ol",
    "video", "th", "h4", "section", "blockquote", "cite", "table", "thead",
    "tbody", "br",
    # seen in page content as well as posts
    "h1", "h5", "h6", "source", "iframe", "sup", "sub", "del", "s", "u",
}

# Structural wrappers with no meaning of their own: unwrap to their children.
UNWRAP = {"span", "section", "div", "u"}

GALLERY_HINTS = ("wp-block-gallery", "gallery", "tiled-gallery", "wp-block-columns")


class ConvertError(ValueError):
    pass


class Stats:
    def __init__(self):
        self.empty_p = 0
        self.empty_heading = 0
        self.equations = 0
        self.images = 0
        self.videos = 0
        self.code_blocks = 0
        self.tables = 0
        self.galleries = 0
        self.raw_html_blocks = 0
        self.captions = 0
        self.unknown_tags = set()


# --------------------------------------------------------------------- media

def local_media_name(url):
    """An origin upload URL -> the filename this post will carry it under."""
    name = unquote(Path(urlparse(un_photon(url)).path).name)
    stem = Path(name).stem
    suffix = Path(name).suffix.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return f"{slug}{suffix}"


def _is_quicklatex(node):
    return "ql-img" in " ".join(node.get("class") or [])


def _equation(node, stats, where):
    """A QuickLaTeX <img> -> inline $...$, recovered from its own alt.

    The alt carries the LaTeX source, HTML-numeric-escaped. BeautifulSoup has
    already unescaped it by the time we see it.
    """
    classes = " ".join(node.get("class") or [])
    if "ql-img-displayed-formula" in classes:
        kind = "display"
    elif "ql-img-inline-formula" in classes:
        kind = "inline"
    else:
        raise ConvertError(
            f"{where}: QuickLaTeX image with an unrecognised class {classes!r}. "
            "A third formula class must stop the build, not be guessed at.")
    latex = (node.get("alt") or "").replace("$$", "").strip()
    if not latex:
        raise ConvertError(
            f"{where}: a QuickLaTeX image has no recoverable alt text: "
            f"{node.get('src')}\n  Record it in overrides/ as an "
            "unrecovered_equation rather than letting the post lose its maths.")
    stats.equations += 1
    return f"$${latex}$$" if kind == "display" else f"${latex}$"


# -------------------------------------------------------------------- inline

def _inline(node, stats, where, media):
    if isinstance(node, NavigableString):
        text = str(node)
        # Escape only what would otherwise become markdown syntax.
        return re.sub(r"([*_`\[\]])", r"\\\1", text)
    if not isinstance(node, Tag):
        return ""

    name = node.name.lower()
    if name not in KNOWN_TAGS:
        stats.unknown_tags.add(name)
        raise ConvertError(
            f"{where}: unknown tag <{name}>. The vocabulary is closed on "
            "purpose — add it to KNOWN_TAGS deliberately, with a rule for what "
            "it becomes. Passing it through silently is how a <video> gets lost.")

    kids = lambda: "".join(_inline(c, stats, where, media) for c in node.children)

    if name == "img":
        if _is_quicklatex(node):
            return _equation(node, stats, where)
        src = un_photon((node.get("src") or "").replace("&#038;", "&"))
        alt = (node.get("alt") or "").strip()
        local = media.register(src, where)
        stats.images += 1
        return f"![{alt}](media/{local})"
    if name in ("strong", "b"):
        inner = kids().strip()
        return f"**{inner}**" if inner else ""
    if name in ("em", "i", "cite"):
        inner = kids().strip()
        return f"_{inner}_" if inner else ""
    if name in ("del", "s"):
        inner = kids().strip()
        return f"~~{inner}~~" if inner else ""
    if name == "code":
        text = node.get_text()
        ticks = "`" * (max((len(m) for m in re.findall(r"`+", text)), default=0) + 1)
        pad = " " if text.startswith("`") or text.endswith("`") else ""
        return f"{ticks}{pad}{text}{pad}{ticks}"
    if name == "a":
        href = un_photon((node.get("href") or "").replace("&#038;", "&"))
        inner = kids().strip()
        if not inner:
            return ""
        if not href:
            return inner
        return f"[{inner}]({href})"
    if name == "br":
        return "  \n"
    if name in ("sup", "sub"):
        return f"<{name}>{kids()}</{name}>"
    if name in UNWRAP:
        return kids()
    # Any remaining block tag met inline is unwrapped rather than dropped.
    return kids()


# --------------------------------------------------------------------- block

def _raw(node, media, where):
    """Emit a subtree as raw HTML, with every media URL localised."""
    clone = BeautifulSoup(str(node), "html.parser")
    for tag in clone.find_all(["img", "video", "source"]):
        src = tag.get("src")
        if src:
            tag["src"] = "media/" + media.register(
                un_photon(src.replace("&#038;", "&")), where)
        for junk in ("srcset", "sizes", "data-recalc-dims", "loading",
                     "decoding", "data-lazy-src", "class", "id", "style"):
            if junk in tag.attrs:
                del tag[junk]
    for tag in clone.find_all(True):
        for junk in ("data-id", "data-element_type", "data-e-type",
                     "data-widget_type", "data-settings"):
            if junk in tag.attrs:
                del tag[junk]
    return str(clone).strip()


def _table(node, stats, where, media):
    rows = []
    for tr in node.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if any(c.get("colspan") or c.get("rowspan") for c in cells):
            # A guard that has never fired on this corpus (measured: zero
            # colspan/rowspan anywhere). If it ever does, the table keeps its
            # structure as raw HTML rather than being flattened into a lie.
            stats.raw_html_blocks += 1
            return _raw(node, media, where)
        rows.append(["".join(_inline(c, stats, where, media)
                             for c in cell.children).strip().replace("|", "\\|")
                     for cell in cells])
    if not rows:
        return ""
    stats.tables += 1
    head, body = rows[0], rows[1:]
    out = ["| " + " | ".join(head) + " |",
           "|" + "|".join("---" for _ in head) + "|"]
    for r in body:
        r = (r + [""] * len(head))[:len(head)]
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def _block(node, stats, where, media, overrides):
    """One block-level node -> markdown (or raw HTML where markdown cannot say it)."""
    if isinstance(node, NavigableString):
        text = str(node).strip()
        return text if text else ""
    if not isinstance(node, Tag):
        return ""

    name = node.name.lower()
    if name not in KNOWN_TAGS:
        stats.unknown_tags.add(name)
        raise ConvertError(f"{where}: unknown tag <{name}> (see KNOWN_TAGS)")

    classes = " ".join(node.get("class") or [])

    # A GALLERY IS A GROUP. Markdown cannot say "these four images are one
    # thing", so losing the grouping changes how the post reads.
    if any(h in classes for h in GALLERY_HINTS) and len(node.find_all("img")) > 1:
        stats.galleries += 1
        stats.raw_html_blocks += 1
        figures = node.find_all("figure")
        stats.images += len(node.find_all("img"))

        if not figures:
            # Nothing to rebuild from: emit the node whole, caption included.
            stats.captions += len([c for c in node.find_all("figcaption")
                                   if c.get_text(strip=True)])
            return f'<div class="sm-gallery">{_raw(node, media, where)}</div>'

        inner = "".join(_raw(f, media, where) for f in figures)
        # Captions on the gallery's own items survive inside that raw HTML,
        # but the gate cannot see them unless they are counted here.
        stats.captions += len([c for f in figures
                               for c in f.find_all("figcaption")
                               if c.get_text(strip=True)])
        grid = f'<div class="sm-gallery">{inner}</div>'

        # THE GALLERY'S OWN CAPTION, which is a DIRECT child of this figure and
        # therefore NOT in find_all("figure") above. Two were silently lost
        # this way, and one of them is the only sentence explaining what an
        # entire grid of images actually is ("each of the above images is an
        # input in the UNET").
        own = [c for c in node.find_all("figcaption", recursive=False)
               if c.get_text(strip=True)]
        if not own:
            return grid
        stats.captions += len(own)
        caps = "".join(f"<figcaption>{c.decode_contents().strip()}</figcaption>"
                       for c in own)
        return f'<figure class="sm-gallery-fig">{grid}{caps}</figure>'

    if name == "figure":
        cap = node.find("figcaption")
        if cap and cap.get_text(strip=True):
            stats.captions += len([c for c in node.find_all("figcaption")
                                   if c.get_text(strip=True)])
            # A caption has no slot in markdown. The alternatives are dropping
            # it (lossy) or emitting an italic paragraph that LOOKS like a
            # caption but is semantically a paragraph -- a lie the renderer
            # then has to guess at forever.
            stats.raw_html_blocks += 1
            stats.images += len(node.find_all("img"))
            stats.videos += len(node.find_all("video"))
            return _raw(node, media, where)
        # No caption: recurse at BLOCK level, not inline. Rendering children
        # inline flattened <figure class="wp-block-table"> into a run of text
        # and lost both of this corpus's tables.
        return "\n\n".join(filter(None, (
            _block(c, stats, where, media, overrides) for c in node.children)))

    if name == "video":
        stats.videos += 1
        stats.raw_html_blocks += 1
        return _raw(node, media, where)

    if name == "pre":
        code = node.find("code")
        text = _html.unescape(code.get_text() if code else node.get_text())
        text = text.rstrip("\n")
        lang = overrides.get("code_language", "")
        fence = "`" * max(3, max((len(m) for m in re.findall(r"`+", text)),
                                 default=0) + 1)
        stats.code_blocks += 1
        return f"{fence}{lang}\n{text}\n{fence}"

    if name == "table":
        return _table(node, stats, where, media)

    if name in ("ul", "ol"):
        items = []
        for i, li in enumerate(node.find_all("li", recursive=False), 1):
            if li.find(["ul", "ol"]):
                raise ConvertError(
                    f"{where}: nested list found. Measured zero in this corpus; "
                    "add a rule for nesting deliberately rather than flattening.")
            inner = "".join(_inline(c, stats, where, media)
                            for c in li.children).strip()
            if inner:
                items.append(f"{i}. {inner}" if name == "ol" else f"- {inner}")
        return "\n".join(items)

    if name == "blockquote":
        inner = "\n\n".join(filter(None, (
            _block(c, stats, where, media, overrides) for c in node.children)))
        return "\n".join("> " + ln if ln else ">" for ln in inner.split("\n"))

    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        inner = "".join(_inline(c, stats, where, media)
                        for c in node.children).strip()
        if not inner:
            stats.empty_heading += 1
            return ""
        level = int(name[1])
        return "#" * max(2, level) + " " + inner

    if name == "hr":
        return "---"

    if name == "p":
        inner = "".join(_inline(c, stats, where, media) for c in node.children)
        if not inner.strip():
            stats.empty_p += 1
            return ""
        return inner.strip()

    if name in UNWRAP:
        return "\n\n".join(filter(None, (
            _block(c, stats, where, media, overrides) for c in node.children)))

    # A VOID ELEMENT AT BLOCK LEVEL. An <img> or <br> has no children, so the
    # children-rendering fallback below returns "" and the image vanishes. 14
    # of the 15 Midjourney images in the gameboy post sit at the document root
    # exactly like this, and the first run of this converter silently dropped
    # every one of them.
    if name in ("img", "br"):
        return _inline(node, stats, where, media).strip()

    # Anything else known but not block-shaped: treat as a paragraph.
    inner = "".join(_inline(c, stats, where, media) for c in node.children).strip()
    return inner


def to_markdown(html_text, where, media, overrides):
    soup = BeautifulSoup(html_text, "html.parser")
    stats = Stats()
    expected_eq = len(soup.select("img[class*=ql-img]"))
    expected_img = len(soup.find_all("img")) - expected_eq
    expected_vid = len(soup.find_all("video"))
    expected_cap = len([c for c in soup.find_all("figcaption")
                        if c.get_text(strip=True)])

    blocks = []
    for child in soup.children:
        out = _block(child, stats, where, media, overrides)
        if out:
            blocks.append(out)
    # One paragraph per line, never wrapped: diffs stay per-paragraph forever.
    body = "\n\n".join(blocks).strip() + "\n"

    # THE GATE. Every one of these caught a real bug on this corpus, and each
    # bug looked exactly like a successful conversion:
    #   - a top-level <img> rendered as nothing (14 of 15 Midjourney images)
    #   - <figure class="wp-block-table"> flattened a table into prose (both)
    #   - `node.find("video")` swallowed a whole Media & Text block and left
    #     18 equations as dead <img> tags pointing at a dying CDN
    # A count that silently disagrees is the only warning you get.
    if stats.equations != expected_eq:
        raise ConvertError(
            f"{where}: {expected_eq} QuickLaTeX images in the source but "
            f"{stats.equations} equations in the output. Every one carries its "
            "LaTeX in its alt; none may be dropped.")
    if stats.images != expected_img:
        raise ConvertError(
            f"{where}: {expected_img} non-equation images in the source but "
            f"{stats.images} in the output.")
    if stats.videos != expected_vid:
        raise ConvertError(
            f"{where}: {expected_vid} videos in the source but {stats.videos} "
            "in the output.")
    if stats.captions != expected_cap:
        raise ConvertError(
            f"{where}: {expected_cap} non-empty figcaptions in the source but "
            f"{stats.captions} in the output. A caption is content — one of "
            "these explains what an entire gallery of images actually is.")
    return body, stats


# ------------------------------------------------------------------- media

class MediaRegistry:
    """Maps every image/video URL a post references to a local filename.

    Resolution order matters. An upload URL resolves against the captured
    media library; a `cdn.midjourney.com` URL resolves against the Wayback
    rescues, because those files were never in the library and are 403 at
    origin. Anything that resolves against neither RAISES — a post silently
    losing an image is the failure this whole migration is built to prevent.
    """

    def __init__(self):
        self.external = {}
        idx = ARCHIVE / "media-original" / "_external" / "_index.json"
        if idx.exists():
            for row in json.loads(idx.read_text(encoding="utf-8")):
                # Keyed on BOTH forms: the markup carries the Photon URL, but
                # the converter has already un-Photoned it by the time we look.
                self.external[row["url"]] = row["path"]
                self.external[un_photon(row["url"])] = row["path"]
        self.entries = {}     # local name -> source path on disk
        self.unresolved = []

    def _archive_path(self, url):
        if url in self.external:
            return ARCHIVE / "media-original" / "_external" / self.external[url]
        parts = urlparse(url).path.split("/wp-content/uploads/", 1)
        if len(parts) == 2:
            p = ARCHIVE / "media-original" / unquote(parts[1])
            if p.exists():
                return p
        name = unquote(Path(urlparse(url).path).name)
        for candidate in (ARCHIVE / "media-original").rglob(name):
            return candidate
        return None

    def register(self, url, where):
        src = self._archive_path(url)
        if src is None:
            self.unresolved.append((where, url))
            raise ConvertError(
                f"{where}: no captured file for {url}\n"
                "  It is in neither the media library nor the Wayback rescues. "
                "Capture it before converting — after cutover it does not exist.")
        if url in self.external:
            # Midjourney originals are .png; keep the content hash as the name
            # so two posts referencing one prompt share a file.
            local = f"midjourney-{Path(self.external[url]).stem[:10]}.png"
        else:
            local = local_media_name(url)
        existing = self.entries.get(local)
        if existing and existing != src:
            local = f"{Path(local).stem}-{abs(hash(url)) % 9973}{Path(local).suffix}"
        self.entries[local] = src
        return local


def load_overrides(slug):
    """Hand-declared per-post facts: code languages, and anything else that
    must not be guessed."""
    path = OVERRIDES / f"{slug}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _fm_value(v):
    if isinstance(v, list):
        return "[" + ", ".join(str(x) for x in v) + "]"
    s = str(v)
    if s == "" or any(c in s for c in ":#[]{}") or s != s.strip():
        return '"' + s.replace('"', "'") + '"'
    return s


# Front-matter keys a HUMAN owns once curation has started. Re-converting must
# never silently revert them -- doing exactly that wiped three published posts
# back to `staged` and lost their summaries, categories and tags, along with
# every media reference that the optimiser had rewritten.
CURATED_KEYS = ("status", "summary", "category", "tags", "updated", "hero",
                "hero_alt", "feed", "noindex", "scripts", "styles", "data",
                "fallback", "permalink", "aliases")


def existing_curation(path):
    """Curated keys already in a post, so a re-convert carries them forward."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    head = text.split("---\n", 2)[1]
    out = {}
    for line in head.split("\n"):
        if ":" not in line or line.startswith((" ", "\t", "-")):
            continue
        key, _, value = line.partition(":")
        if key.strip() in CURATED_KEYS:
            out[key.strip()] = value.strip()
    return out


def convert_post(post, terms, force=False):
    slug = post["slug"]
    out_dir = POSTS_OUT / slug
    where = f"{slug}"
    overrides = load_overrides(slug)
    media = MediaRegistry()

    body, stats = to_markdown(post["content"]["rendered"], where, media, overrides)

    cats = [terms["categories"].get(i, str(i)) for i in post.get("categories", [])]
    tags = [terms["tags"].get(i, str(i)) for i in post.get("tags", [])]
    excerpt = re.sub(r"<[^>]+>", "", post.get("excerpt", {}).get("rendered", ""))
    excerpt = _html.unescape(excerpt).strip().replace("\n", " ")
    excerpt = re.sub(r"\s+", " ", excerpt)

    fm = {
        "title": _html.unescape(post["title"]["rendered"]),
        "slug": slug,
        "date": post["date_gmt"][:10],
        "status": "staged",
        "wp_id": post["id"],
        "wp_link": post["link"],
        "wp_excerpt": excerpt,
        "wp_categories": cats,
        "wp_tags": tags,
        "source": "wordpress-rest-v2",
    }
    if post.get("modified_gmt", "")[:10] != post["date_gmt"][:10]:
        fm["updated"] = post["modified_gmt"][:10]
    # featured_media is 0 on every post in this corpus: no hero image was ever
    # chosen. The key is OMITTED rather than written as null -- absent means
    # absent, and `hero: null` would read as a hero that failed to resolve.
    if post.get("featured_media"):
        fm["hero"] = "?"

    # Carry forward anything a human decided. `status` in particular: without
    # this, a re-convert quietly unpublishes every published post.
    index = out_dir / "index.md"
    curated = existing_curation(index)
    fm.update(curated)

    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {v if k in curated else _fm_value(v)}")
    lines += ["---", "", body]

    out_dir.mkdir(parents=True, exist_ok=True)
    index.write_text("\n".join(lines), encoding="utf-8")
    return stats, media, curated


def main():
    posts = json.loads((ARCHIVE / "wp-api" / "posts.json").read_text(encoding="utf-8"))
    terms = {}
    for kind in ("categories", "tags"):
        rows = json.loads((ARCHIVE / "wp-api" / f"{kind}.json").read_text(encoding="utf-8"))
        terms[kind] = {r["id"]: r["name"] for r in rows}

    assert len(posts) >= 12, f"only {len(posts)} posts in the archive"
    POSTS_OUT.mkdir(parents=True, exist_ok=True)

    print(f"{'slug':46} {'words':>6} {'img':>4} {'eq':>4} {'code':>5} "
          f"{'tbl':>4} {'vid':>4} {'gal':>4} {'empty-p':>8}")
    total = {"images": 0, "equations": 0, "code_blocks": 0, "tables": 0,
             "videos": 0, "galleries": 0, "empty_p": 0}
    media_plan, failures, kept = {}, [], []
    for post in sorted(posts, key=lambda p: p["date_gmt"]):
        try:
            stats, media, curated = convert_post(post, terms)
        except ConvertError as exc:
            failures.append((post["slug"], str(exc)))
            print(f"{post['slug'][:44]:46}  !! {str(exc).splitlines()[0][:60]}")
            continue
        body = (POSTS_OUT / post["slug"] / "index.md").read_text(encoding="utf-8")
        words = len(re.sub(r"[#*_`>|\-]", " ", body.split("---", 2)[-1]).split())
        print(f"{post['slug'][:44]:46} {words:>6} {stats.images:>4} "
              f"{stats.equations:>4} {stats.code_blocks:>5} {stats.tables:>4} "
              f"{stats.videos:>4} {stats.galleries:>4} {stats.empty_p:>8}")
        if curated:
            kept.append(f"{post['slug']}: kept {', '.join(sorted(curated))}")
        for k in total:
            total[k] += getattr(stats, k)
        media_plan[post["slug"]] = {k: str(v) for k, v in media.entries.items()}

    print(f"\n{'TOTAL':46} {'':>6} {total['images']:>4} {total['equations']:>4} "
          f"{total['code_blocks']:>5} {total['tables']:>4} {total['videos']:>4} "
          f"{total['galleries']:>4} {total['empty_p']:>8}")
    (ARCHIVE / "media_plan.json").write_text(
        json.dumps(media_plan, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nmedia plan -> archive/media_plan.json "
          f"({sum(len(v) for v in media_plan.values())} files across "
          f"{len(media_plan)} posts)")
    if kept:
        print(f"\ncurated front matter carried forward on {len(kept)} post(s):")
        for line in kept:
            print(f"  {line}")
        print("  (re-run migrate/media.py to rewrite media references)")
    if failures:
        print(f"\n{len(failures)} POST(S) FAILED TO CONVERT:")
        for slug, msg in failures:
            print(f"\n  {slug}:\n    " + msg.replace("\n", "\n    "))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
