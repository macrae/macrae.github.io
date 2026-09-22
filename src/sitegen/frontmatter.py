"""Front matter: a closed vocabulary, parsed by hand.

NOT PyYAML, and the reason is determinism. YAML coerces `no` to False, coerces
`2019-03-04` to a datetime.date, treats `1.10` as a float that round-trips as
`1.1`, and has changed those semantics between releases. This build's entire
claim is that the same content produces the same bytes, so the content layer is
the last place to accept a parser that decides what a string means.

Everything here stays `str` until the SCHEMA says otherwise, and an unknown key
is a build ERROR rather than a warning. A closed vocabulary is what lets the
validator build its script allowlist from the corpus instead of from a second
hand-maintained list that can drift.

Supported grammar, deliberately small:

    key: scalar                 # quotes optional, stripped if present
    key: [a, b, c]              # flow sequence
    key:                        # block sequence of scalars
      - a
      - b
    scripts:                    # block sequence of flat maps
      - src: js/chart.js
        defer: true
"""

import re
from pathlib import Path

from . import spec

FENCE = "---"

# name -> (kind, required_when)
#   kind: "str" | "date" | "list" | "bool" | "maps"
#   required_when: "always" | "published" | None
SCHEMA = {
    # identity — a file without these cannot be placed at all
    "title":   ("str",  "always"),
    "slug":    ("str",  "always"),
    "date":    ("date", "always"),
    "status":  ("str",  "always"),

    # curation — REQUIRED ONLY TO PUBLISH. A staged post is raw material
    # straight off WordPress and has not been through curation yet; requiring a
    # category on it would mean inventing one at import time, which is exactly
    # the guess this migration refuses to make. Requiring it to PUBLISH means
    # you cannot ship a post without having chosen.
    "summary":  ("str",  "published"),
    "category": ("str",  "published"),
    "tags":     ("list", "published"),

    # optional
    "updated":   ("date", None),
    "permalink": ("str",  None),
    "aliases":   ("list", None),
    "hero":      ("str",  None),
    "hero_alt":  ("str",  None),
    "feed":      ("bool", None),
    "noindex":   ("bool", None),

    # the interactive opt-in. `fallback` is not optional in the presence of
    # `scripts`; that is checked in validate(), not here, because it is a
    # relationship between keys rather than a property of one.
    "scripts":  ("maps", None),
    "styles":   ("list", None),
    "data":     ("list", None),
    "fallback": ("str",  None),

    # provenance from the WordPress import. Rendered nowhere. `wp_excerpt` is
    # NOT called `description`: WordPress generated it from the opening words,
    # and naming it a description would put an unwritten sentence under his
    # byline.
    "wp_id":         ("str",  None),
    "wp_link":       ("str",  None),
    "wp_excerpt":    ("str",  None),
    "wp_categories": ("list", None),
    "wp_tags":       ("list", None),
    "source":        ("str",  None),
    "captured":      ("str",  None),
}

DEFAULTS = {"feed": True, "noindex": False}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class FrontMatterError(ValueError):
    """Always carries the file path. An error that does not name the file costs
    five minutes every single time."""


def _unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _split(text, where):
    """Return (front matter text, body text)."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != FENCE:
        raise FrontMatterError(f"{where}: file does not start with a '{FENCE}' fence")
    for i in range(1, len(lines)):
        if lines[i].strip() == FENCE:
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:]).lstrip("\n")
    raise FrontMatterError(f"{where}: front matter is never closed by a '{FENCE}' fence")


def _parse_block(raw, where):
    """The grammar in the module docstring, and nothing else."""
    data, key, i = {}, None, 0
    lines = raw.split("\n")
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if not line.startswith((" ", "\t", "-")):
            if ":" not in line:
                raise FrontMatterError(f"{where}: line {i + 1} is not 'key: value': {line!r}")
            key, _, value = line.partition(":")
            key, value = key.strip(), value.strip()
            if key in data:
                raise FrontMatterError(f"{where}: duplicate key {key!r}")
            if value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                data[key] = [_unquote(p) for p in inner.split(",") if p.strip()] if inner else []
            elif value:
                data[key] = _unquote(value)
            else:
                data[key] = []          # a block sequence follows, or it is empty
            i += 1
            continue

        stripped = line.strip()
        if not stripped.startswith("- "):
            raise FrontMatterError(
                f"{where}: line {i + 1} is indented but not a '- ' item: {line!r}")
        if key is None:
            raise FrontMatterError(f"{where}: line {i + 1} is a list item with no key")
        item = stripped[2:].strip()
        if not isinstance(data.get(key), list):
            raise FrontMatterError(f"{where}: {key!r} has both a value and list items")
        if ":" in item and not item.startswith(("http://", "https://", "/")):
            # a flat map: consume this line and every deeper-indented one
            indent = len(line) - len(line.lstrip())
            entry = {}
            k, _, v = item.partition(":")
            entry[k.strip()] = _unquote(v)
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    i += 1
                    continue
                nindent = len(nxt) - len(nxt.lstrip())
                if nindent <= indent or nxt.strip().startswith("- "):
                    break
                k, _, v = nxt.strip().partition(":")
                entry[k.strip()] = _unquote(v)
                i += 1
            data[key].append(entry)
            continue
        data[key].append(_unquote(item))
        i += 1
    return data


def _coerce(data, where):
    out = dict(DEFAULTS)
    for key, value in data.items():
        if key not in SCHEMA:
            raise FrontMatterError(
                f"{where}: unknown front-matter key {key!r}.\n"
                f"  The vocabulary is closed — add it to frontmatter.SCHEMA if it "
                f"is real, or fix the typo.\n"
                f"  Known keys: {', '.join(sorted(SCHEMA))}")
        kind = SCHEMA[key][0]
        if kind == "list":
            if not isinstance(value, list):
                raise FrontMatterError(f"{where}: {key!r} must be a list, got {value!r}")
            out[key] = [str(v) for v in value]
        elif kind == "maps":
            if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
                raise FrontMatterError(
                    f"{where}: {key!r} must be a list of maps, e.g.\n"
                    f"    {key}:\n      - src: js/chart.js\n        defer: true")
            out[key] = value
        elif kind == "bool":
            if str(value).lower() not in ("true", "false"):
                raise FrontMatterError(
                    f"{where}: {key!r} must be literally true or false, got {value!r}. "
                    "This parser does not guess at yes/no/on/off — that is the "
                    "YAML behaviour it exists to avoid.")
            out[key] = str(value).lower() == "true"
        elif kind == "date":
            if not DATE_RE.match(str(value)):
                raise FrontMatterError(
                    f"{where}: {key!r} must be YYYY-MM-DD, got {value!r}")
            out[key] = str(value)       # stays a STRING; never a date object
        else:
            if isinstance(value, list):
                raise FrontMatterError(f"{where}: {key!r} must be a scalar, got a list")
            out[key] = str(value)
    return out


def validate(data, where):
    status = data.get("status")
    if status is None:
        raise FrontMatterError(
            f"{where}: no `status`. It is required and has no default — "
            "publishing-by-omission and archiving-by-omission are both wrong.")
    if status not in spec.STATUSES:
        raise FrontMatterError(
            f"{where}: status {status!r} is not one of {', '.join(spec.STATUSES)}")

    for key, (_, required) in SCHEMA.items():
        if required == "always" and key not in data:
            raise FrontMatterError(f"{where}: missing required key {key!r}")
        if required == "published" and status == "published" and key not in data:
            raise FrontMatterError(
                f"{where}: {key!r} is required to publish. A staged post may go "
                "without it; a published one may not — that is what makes "
                "curation a decision rather than an omission.")

    if status == "published":
        cat = data.get("category")
        if cat not in spec.CATEGORIES:
            raise FrontMatterError(
                f"{where}: category {cat!r} is not in the closed vocabulary "
                f"({', '.join(spec.CATEGORIES)}). Add it to spec.CATEGORIES "
                "deliberately, or use one that exists.")
        for tag in data.get("tags", []):
            if tag not in spec.TAGS:
                raise FrontMatterError(
                    f"{where}: tag {tag!r} is not in spec.TAGS. The vocabulary is "
                    "closed so that a typo cannot silently create a one-member "
                    "tag page — which is how the WordPress taxonomy ended up with "
                    "16 tags used exactly once.")

    if data.get("scripts") and not data.get("fallback"):
        raise FrontMatterError(
            f"{where}: declares `scripts` but no `fallback`.\n"
            "  Every interactive page must name a static figure to show in "
            "<noscript>, so the argument is complete with JavaScript off. This "
            "is refused at build time, not reported later.")
    for entry in data.get("scripts", []):
        if "src" not in entry:
            raise FrontMatterError(f"{where}: a `scripts` entry has no `src`")
        if entry["src"].startswith(("http://", "https://", "//")):
            raise FrontMatterError(
                f"{where}: script {entry['src']!r} is remote. Scripts must be "
                "committed local files — a CDN is a third party who can change "
                "your page after you built it, and it breaks offline and print.")
    return data


def parse(text, where="<string>"):
    """text -> (metadata dict, body markdown)."""
    raw, body = _split(text, where)
    return validate(_coerce(_parse_block(raw, where), where), where), body


def load(path):
    path = Path(path)
    return parse(path.read_text(encoding="utf-8"), where=str(path))
