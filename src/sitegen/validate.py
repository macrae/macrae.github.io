"""Check the RENDERED tree. Structure only.

WHAT THIS DELIBERATELY DOES NOT CHECK: whether the prose is any good, whether
an essay is finished, whether alt text is well written, or whether an external
link is still alive. None of that is mechanically decidable, and a validator
that fires on correct data is worse than no validator at all. That rule has
already been proved twice in this repository — once by a check that read raw
source and failed on a comment warning against the very thing it forbade, and
once by an animation check that asserted frame-count equality when WebP
legitimately deduplicates identical frames.

Every check below can be decided from the bytes on disk.
"""

import argparse
import re
import sys
from pathlib import Path

from . import content, design, spec

ROOT = Path(__file__).resolve().parent.parent.parent

# The ONE link that may not resolve inside this tree. /mana-map/ is served by
# macrae/mana-map as a GitHub project site under this user site's custom
# domain — a different repository entirely. Any other unresolvable internal
# link is a bug. The allowlist has exactly one entry and a test asserts that.
EXTERNAL_REPO_PATHS = ("/mana-map/",)

TAG_RE = re.compile(r"<(\w+)\b([^>]*)>", re.I)
ATTR_RE = re.compile(r'(\w[\w:-]*)\s*=\s*"([^"]*)"')


class Report:
    def __init__(self):
        self.errors, self.notes = [], []

    def error(self, where, msg):
        self.errors.append(f"{where}: {msg}")

    def note(self, where, msg):
        self.notes.append(f"{where}: {msg}")


def _attrs(blob):
    return dict(ATTR_RE.findall(blob))


def check_tree(root, corpus, report):
    root = Path(root)
    pages = sorted(root.rglob("*.html"))
    if not pages:
        report.error(str(root), "no HTML pages at all — did the build run?")
        return

    # The script allowlist is derived FROM THE CORPUS, not from a second
    # hand-maintained list, so the two cannot drift apart.
    allowed = {}
    for entry in corpus.all_entries:
        page = str(Path(entry.output_path))
        allowed[page] = {s["src"].split("/")[-1] for s in entry.meta.get("scripts", [])}
        if entry.meta.get("scripts") and not entry.meta.get("fallback"):
            report.error(page, "declares scripts but no fallback")

    checked_links = checked_scripts = checked_imgs = 0

    for page in pages:
        rel = str(page.relative_to(root))
        html = page.read_text(encoding="utf-8")

        # ---- the shell every page must carry
        if "<html lang=" not in html:
            report.error(rel, "no lang attribute on <html>")
        if "<title>" not in html:
            report.error(rel, "no <title>")
        if 'rel="canonical"' not in html:
            report.error(rel, "no canonical link")
        if rel != "404.html" and 'name="description"' not in html:
            report.note(rel, "no meta description")

        # ---- scripts
        for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", html, re.I | re.S):
            checked_scripts += 1
            attrs, body = _attrs(m.group(1)), m.group(2)
            if body.strip():
                report.error(rel, "inline <script> body — scripts must be "
                                  "external files so every byte is diffable")
            src = attrs.get("src", "")
            if not src:
                report.error(rel, "<script> with no src")
                continue
            if src.startswith(("http://", "https://", "//")):
                report.error(rel, f"remote script {src!r} — a CDN is a third "
                                  "party who can change the page after you built it")
            elif src.split("/")[-1] not in allowed.get(rel, set()):
                report.error(rel, f"undeclared script {src!r}; the page's front "
                                  "matter does not list it")
        if re.search(r"<script", html, re.I) and "<noscript" not in html:
            report.error(rel, "has a script but no <noscript> fallback")

        # Scripts wearing a different hat. The precedent's regex missed both.
        for m in re.finditer(r'\son[a-z]+\s*=\s*"', html, re.I):
            report.error(rel, f"inline event handler near offset {m.start()}")
        if re.search(r'(?:href|src)\s*=\s*"\s*javascript:', html, re.I):
            report.error(rel, "javascript: URL")

        # ---- images
        for m in re.finditer(r"<img\b([^>]*)>", html, re.I):
            checked_imgs += 1
            attrs = _attrs(m.group(1))
            if "alt" not in attrs:
                report.error(rel, f"<img src={attrs.get('src','?')!r} has no alt "
                                  "attribute (alt=\"\" is legal for decorative)")

        # ---- links and anchors
        ids = set(re.findall(r'\sid="([^"]+)"', html))
        for m in re.finditer(r'(?:href|src)="([^"]+)"', html):
            target = m.group(1)
            if target.startswith(("http://", "https://", "mailto:", "//", "data:")):
                continue
            checked_links += 1
            if target.startswith("#"):
                if target[1:] and target[1:] not in ids:
                    report.error(rel, f"anchor {target} has no matching id on "
                                      "this page")
                continue
            path_part = target.split("#")[0].split("?")[0]
            if not path_part:
                continue
            if path_part in EXTERNAL_REPO_PATHS:
                continue
            base = root if path_part.startswith("/") else page.parent
            resolved = base / path_part.lstrip("/")
            if path_part.endswith("/"):
                resolved = resolved / "index.html"
            if not resolved.exists():
                report.error(rel, f"broken link {target!r}")

    # ---- the files whose absence takes the site down
    cname = root / "CNAME"
    if spec.CUSTOM_DOMAIN_LIVE:
        if not cname.exists():
            report.error("CNAME", "missing — the custom domain stops working")
        elif cname.read_text(encoding="utf-8").strip() != spec.CNAME:
            report.error("CNAME", f"says {cname.read_text().strip()!r}, "
                                  f"expected {spec.CNAME!r}")
    elif cname.exists():
        report.error("CNAME", "present while spec.CUSTOM_DOMAIN_LIVE is False — "
                              "this redirects macrae.github.io to the domain, "
                              "which still serves WordPress")
    else:
        report.note("CNAME", "absent by design; the site serves at "
                             "macrae.github.io until the domain is cut over")
    if not (root / ".nojekyll").exists():
        report.error(".nojekyll", "missing — Pages will run Jekyll over the tree "
                                  "and silently drop anything starting with _")
    if not (root / "404.html").exists():
        report.error("404.html", "missing from the publish root")

    # ---- the stylesheet must match the constant that generated it
    css_path = root / spec.path_for("stylesheet")
    if not css_path.exists():
        report.error("site.css", "missing")
    else:
        css = css_path.read_text(encoding="utf-8")
        if css != design.stylesheet():
            report.error("site.css", "does not match design.SITE_CSS — it was "
                                     "hand-edited, and the next build will "
                                     "overwrite it")
        used = set(re.findall(r"var\((--[a-z0-9-]+)", css))
        defined = set(re.findall(r"^\s*(--[a-z0-9-]+)\s*:", css, re.M))
        for token in sorted(used - defined):
            report.error("site.css", f"{token} is used but never defined")
        for token in sorted(used | defined):
            if not token.startswith("--sm-"):
                report.error("site.css", f"{token} is not --sm- namespaced; "
                                         "these tokens are a permanent fork")

    # ---- reserved slugs
    for entry in corpus.essays:
        if entry.slug in spec.RESERVED_SLUGS:
            report.error(entry.slug, "is a reserved slug")

    report.note("summary", f"{len(pages)} pages, {checked_links} links, "
                           f"{checked_imgs} images, {checked_scripts} scripts")
    assert checked_links >= 20, f"only {checked_links} links checked — the tree looks empty"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate the rendered tree.")
    ap.add_argument("root", nargs="?", default="docs")
    ap.add_argument("--include-unpublished", action="store_true")
    args = ap.parse_args(argv)

    corpus = content.load(include_unpublished=args.include_unpublished)
    report = Report()
    check_tree(args.root, corpus, report)

    for note in report.notes:
        print(f"NOTE  {note}")
    for err in report.errors:
        print(f"FAIL  {err}")
    if report.errors:
        print(f"\n{len(report.errors)} problem(s)")
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
