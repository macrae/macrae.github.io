"""The corpus: the single source of what exists.

Nothing downstream touches the filesystem to discover content. Everything is
parsed once, here, and handed on as an immutable Corpus — which is what makes
the build a pure function of content/ and therefore byte-identically
repeatable.

EVERY DIRECTORY WALK IS SORTED. `Path.glob` yields filesystem order, which on
one machine is creation order and on another is inode order; an unsorted walk
produces a different feed, a different index and a different set of bytes on a
colleague's laptop than on yours, and the byte-diff gate would then fail for a
reason nobody could reproduce.

This module also enforces the laws that span FILES rather than living inside
one, which is why they cannot be in frontmatter.py: a slug matching its own
directory, no two posts claiming one URL, and every path a post declares
actually existing on disk.
"""

from dataclasses import dataclass, field
from pathlib import Path

from . import frontmatter, spec

ROOT = Path(__file__).resolve().parent.parent.parent
CONTENT = ROOT / "content"
POSTS = CONTENT / "posts"
PROJECTS = CONTENT / "projects"
FRAGMENTS = CONTENT / "fragments"


@dataclass(frozen=True)
class Entry:
    """One authored thing: an essay or a project page."""
    slug: str
    kind: str                 # "essay" | "project"
    meta: dict
    body: str
    directory: Path

    @property
    def title(self):
        return self.meta["title"]

    @property
    def date(self):
        return self.meta["date"]

    @property
    def status(self):
        return self.meta["status"]

    @property
    def published(self):
        return self.meta["status"] == "published"

    @property
    def category(self):
        return self.meta.get("category")

    @property
    def tags(self):
        return tuple(self.meta.get("tags", ()))

    @property
    def interactive(self):
        return bool(self.meta.get("scripts"))

    @property
    def url(self):
        return spec.url_for(self.kind, slug=self.slug)

    @property
    def output_path(self):
        return spec.path_for(self.kind, slug=self.slug)


@dataclass(frozen=True)
class Corpus:
    essays: tuple = ()
    projects: tuple = ()
    fragments: dict = field(default_factory=dict)
    all_entries: tuple = ()

    def by_category(self):
        out = {}
        for e in self.essays:
            if e.category:
                out.setdefault(e.category, []).append(e)
        return {k: tuple(v) for k, v in sorted(out.items())}

    def by_tag(self):
        out = {}
        for e in self.essays:
            for t in e.tags:
                out.setdefault(t, []).append(e)
        return {k: tuple(v) for k, v in sorted(out.items())}

    def latest_date(self):
        """The newest date in the corpus. The feed's <updated> uses this and
        never the clock — a feed stamped with 'now' changes on every build and
        destroys the byte-identical rebuild."""
        dates = [e.date for e in self.essays] or ["1970-01-01"]
        return max(dates)


class ContentError(ValueError):
    pass


def _load_dir(base, kind, include_unpublished):
    entries = []
    if not base.exists():
        return entries
    for directory in sorted(p for p in base.iterdir() if p.is_dir()):
        index = directory / "index.md"
        if not index.exists():
            raise ContentError(
                f"{directory}: has no index.md. An entry is a DIRECTORY so its "
                "figures, scripts and data sit beside it and move with it when "
                "it is renamed.")
        meta, body = frontmatter.load(index)

        if meta["slug"] != directory.name:
            raise ContentError(
                f"{index}: slug is {meta['slug']!r} but the directory is "
                f"{directory.name!r}. The directory name is the URL; they must agree.")
        if kind == "essay" and meta["slug"] in spec.RESERVED_SLUGS:
            raise ContentError(
                f"{index}: slug {meta['slug']!r} is reserved. "
                + ("That path is served by a DIFFERENT REPOSITORY (macrae/mana-map)."
                   if meta["slug"] == "mana-map" else
                   "A generated page already owns that top-level path."))

        for key in ("fallback", "hero"):
            rel = meta.get(key)
            if rel and not (directory / rel).exists():
                raise ContentError(f"{index}: {key} names {rel!r}, which does not exist")
        for entry in meta.get("scripts", []):
            src = entry["src"]
            if not (directory / src).resolve().exists():
                raise ContentError(
                    f"{index}: script {src!r} does not exist. Scripts must be "
                    "committed local files.")
        for rel in list(meta.get("styles", [])) + list(meta.get("data", [])):
            if not (directory / rel).resolve().exists():
                raise ContentError(f"{index}: declares {rel!r}, which does not exist")

        entry = Entry(slug=meta["slug"], kind=kind, meta=meta, body=body,
                      directory=directory)
        if entry.published or include_unpublished:
            entries.append(entry)
    return entries


def load(include_unpublished=False):
    """Read content/ into a Corpus. The ONLY filesystem discovery in the build.

    `include_unpublished` exists for the local preview and is threaded through
    the SAME renderer rather than a second code path — a renderer kept behind a
    flag is a renderer nobody is testing.
    """
    essays = _load_dir(POSTS, "essay", include_unpublished)
    projects = _load_dir(PROJECTS, "project", include_unpublished)

    seen = {}
    for e in essays + projects:
        if e.slug in seen:
            raise ContentError(f"two entries claim the slug {e.slug!r}")
        seen[e.slug] = e
        for alias in e.meta.get("aliases", []):
            key = alias.strip("/")
            if key in seen:
                raise ContentError(f"alias {alias!r} on {e.slug!r} collides with {key!r}")

    # Newest first, slug breaking ties so two posts on one day cannot reorder
    # between machines.
    essays.sort(key=lambda e: (e.date, e.slug), reverse=True)
    projects.sort(key=lambda e: (e.date, e.slug), reverse=True)

    fragments = {}
    if FRAGMENTS.exists():
        for path in sorted(FRAGMENTS.glob("*.md")):
            fragments[path.stem] = path.read_text(encoding="utf-8")

    return Corpus(essays=tuple(essays), projects=tuple(projects),
                  fragments=fragments, all_entries=tuple(essays + projects))


def fragment(corpus, name):
    """A named authored block embedded in a GENERATED page.

    This is the escape hatch that keeps 'a page is authored or generated, never
    both' honest. The fragment is its own file with its own key, so a
    regenerated list can never clobber an edited sentence.
    """
    if name not in corpus.fragments:
        raise ContentError(
            f"no fragment named {name!r} in content/fragments/. "
            f"Have: {', '.join(sorted(corpus.fragments)) or '(none)'}")
    return corpus.fragments[name]
