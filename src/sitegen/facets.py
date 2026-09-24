"""How the gallery groups itself, derived at BUILD time.

Nothing is stored on the image record. The lexicon in
content/gallery/facets.json is the single source, so editing it takes effect
on the next build with nothing to re-run and no stale copy to disagree with.
For a few hundred images the work is trivial.

THREE KINDS OF FACET, and the distinction is the honest part:

  field    read straight off the record. `collection` and `tags` are the
           author's; nothing infers them.
  derived  computed from stored metadata -- pixel dimensions, Midjourney
           parameters. Always true.
  lexicon  matched against prompt text. THIS IS THE ONLY KIND THAT CAN BE
           WRONG, which is why its terms are written down in a file the
           author can read and change rather than inferred by something they
           would have to argue with.

Matching is on WHOLE WORDS. Substring matching would file every prompt
containing "goldfish" under gold, and a facet that is wrong is worse than a
facet that is missing -- the reader cannot tell it is wrong, they just get the
wrong pictures.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFS = ROOT / "content" / "gallery" / "facets.json"

_CACHE = {}


def definitions():
    if "groups" not in _CACHE:
        if not DEFS.exists():
            _CACHE["groups"] = []
        else:
            data = json.loads(DEFS.read_text(encoding="utf-8"))
            _CACHE["groups"] = [g for g in data.get("groups", []) if g.get("key")]
    return _CACHE["groups"]


def orientation(image):
    """Square, landscape or portrait, from the pixels. Never a guess.

    The 5% band stops a 1024x1020 image being called landscape, which is true
    and useless."""
    w, h = image.get("width", 0), image.get("height", 0)
    if not w or not h:
        return None
    ratio = w / h
    if 0.95 <= ratio <= 1.05:
        return "square"
    return "landscape" if ratio > 1 else "portrait"


def _words(text):
    return set(re.findall(r"[a-z0-9][a-z0-9'-]*", (text or "").lower()))


def lexicon_hits(image, terms):
    """Whole-word matches only. Hyphenated terms are checked as phrases too,
    because "battle-scarred" survives tokenisation in some prompts and splits
    in others."""
    prompt = (image.get("prompt") or "").lower()
    words = _words(prompt)
    out = []
    for label, needles in sorted(terms.items()):
        for needle in needles:
            n = needle.lower()
            if n in words or ("-" in n and n in prompt) or (" " in n and n in prompt):
                out.append(label)
                break
    return out


def for_image(image):
    """{group key: [values]} for one image."""
    out = {}
    params = image.get("parameters") or {}
    for group in definitions():
        key, source = group["key"], group.get("source", "")
        values = []

        if source == "field:collection":
            if image.get("collection"):
                values = [image["collection"]]
        elif source == "field:tags":
            values = list(image.get("tags") or [])
        elif source == "derived:year":
            # From the date Midjourney recorded in the file, never from a
            # clock and never from the filename.
            date = (image.get("date") or "")[:4]
            values = [date] if date.isdigit() else []
        elif source == "derived:orientation":
            o = orientation(image)
            values = [o] if o else []
        elif source.startswith("derived:parameter:"):
            name = source.split(":")[-1]
            raw = params.get(name)
            if raw and raw is not True:
                values = [f"{group.get('prefix', '')}{raw}"]
        elif source == "lexicon":
            values = lexicon_hits(image, group.get("terms") or {})

        if values:
            out[key] = values
    return out


def panel(images):
    """The side panel: groups, in declared order, with counts.

    A group with nothing in it is omitted entirely rather than rendered empty.
    An empty facet is a promise the collection does not keep.
    """
    per_image = [for_image(i) for i in images]
    groups = []
    for group in definitions():
        counts = {}
        for facets in per_image:
            for value in facets.get(group["key"], []):
                counts[value] = counts.get(value, 0) + 1
        if not counts:
            continue
        # Commonest first, then alphabetical: the useful ones surface without
        # the order jittering between builds.
        values = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        groups.append({
            "key": group["key"],
            "label": group.get("label", group["key"]),
            "kind": group.get("source", "").split(":")[0],
            "values": values,
        })
    return groups, per_image
