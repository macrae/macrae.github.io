"""The build: PLAN, then WRITE, then PRUNE.

Every intended output path is computed to bytes IN MEMORY first, then written,
then every file under the publish root that is not in the plan is deleted.

Two reasons the order is this and not the obvious one.

PRUNE IS WHAT MAKES THE CI GATE TOTAL. A site writes a tree, not one file, so a
renamed slug leaves an orphan docs/old-slug/index.html that nothing rewrites
and `git diff` never notices. Without a prune step the gate is blind to exactly
the change most likely to happen.

PLANNING IN MEMORY MEANS A FAILURE LEAVES THE TREE ALONE. An exception halfway
through writing would otherwise leave a half-built site that looks deployable.

The build must be HERMETIC: no network, no clock, no environment reads. That is
why `make migrate` is a separate target — the property is structural rather
than promised.
"""

import argparse
import shutil
import sys
from pathlib import Path

from . import content, design, feed, render, sitemap, spec

ROOT = Path(__file__).resolve().parent.parent.parent
PUBLISH = ROOT / "docs"


def plan(corpus, *, check_internal=None):
    """{relative path: bytes}. The whole site, computed and not yet written."""
    out = {}

    def put(kind, text, **kw):
        out[spec.path_for(kind, **kw)] = text.encode("utf-8")

    put("home", render.render_home(corpus))
    put("writing", render.render_writing_index(corpus))
    put("projects", render.render_projects(corpus))
    put("about", render.render_about(corpus))
    put("notfound", render.render_404(corpus))
    put("stylesheet", design.stylesheet())
    put("feed", feed.render_feed(corpus))
    put("sitemap", sitemap.render_sitemap(corpus))
    put("robots", sitemap.render_robots(corpus))

    for category in corpus.by_category():
        put("category", render.render_category_index(corpus, category),
            category=category)
    for tag in corpus.by_tag():
        put("tag", render.render_tag_index(corpus, tag), tag=tag)

    for entry in corpus.essays:
        put("essay", render.render_essay(corpus, entry, check_internal),
            slug=entry.slug)
    for entry in corpus.projects:
        if entry.slug == "about":
            continue
        put("project", render.render_project(corpus, entry, check_internal),
            slug=entry.slug)

    # Assets an entry declares, copied verbatim beside its page. Images are
    # committed PRE-OPTIMISED: resizing at build time would make the output
    # depend on a compiled library's version, and the byte-diff gate would then
    # fail on a machine with a different Pillow.
    for entry in corpus.all_entries:
        base = Path(entry.output_path).parent
        for sub in ("fig", "js", "data", "media"):
            d = entry.directory / sub
            if not d.is_dir():
                continue
            for path in sorted(p for p in d.rglob("*") if p.is_file()):
                rel = path.relative_to(entry.directory)
                out[str(base / rel)] = path.read_bytes()

    shared = ROOT / "content" / "assets"
    if shared.is_dir():
        for path in sorted(p for p in shared.rglob("*") if p.is_file()):
            out[str(Path("assets") / path.relative_to(shared))] = path.read_bytes()
    return out


def write(pages, root=PUBLISH, prune=True):
    root.mkdir(parents=True, exist_ok=True)
    written = []
    for rel, blob in sorted(pages.items()):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_bytes() != blob:
            path.write_bytes(blob)
        written.append(rel)

    # The two files nothing generates and whose loss takes the site down.
    (root / ".nojekyll").write_text("", encoding="utf-8")
    (root / "CNAME").write_text(spec.CNAME + "\n", encoding="utf-8")

    removed = []
    if prune:
        keep = set(pages) | set(spec.PINNED)
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            rel = str(path.relative_to(root))
            if rel not in keep:
                path.unlink()
                removed.append(rel)
        for d in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
            if not any(d.iterdir()):
                d.rmdir()
    return written, removed


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the site into docs/.")
    ap.add_argument("--include-unpublished", action="store_true",
                    help="preview staged and archived entries too (never for deploy)")
    ap.add_argument("--out", default=None, help="write somewhere other than docs/")
    ap.add_argument("--no-prune", action="store_true")
    args = ap.parse_args(argv)

    root = Path(args.out).resolve() if args.out else PUBLISH
    if args.include_unpublished and root == PUBLISH:
        ap.error("--include-unpublished refuses to write docs/: an unpublished "
                 "entry must never reach the deployed tree. Pass --out.")

    corpus = content.load(include_unpublished=args.include_unpublished)
    pages = plan(corpus)
    written, removed = write(pages, root=root, prune=not args.no_prune)

    print(f"{len(written)} files -> {root.relative_to(ROOT) if root.is_relative_to(ROOT) else root}")
    print(f"  {len(corpus.essays)} essays, {len(corpus.projects)} projects, "
          f"{len(corpus.by_category())} categories, {len(corpus.by_tag())} tags")
    if removed:
        print(f"  pruned {len(removed)}: {', '.join(removed[:6])}"
              + (" ..." if len(removed) > 6 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
