"""Ingest images into the gallery. Re-runnable, and it never overwrites a decision.

Point it at a folder of Midjourney downloads:

    python tools/gallery_ingest.py ~/Downloads/midjourney

Midjourney names files `<user>_<prompt>_<job-uuid>.png`, so a plain folder of
downloads is largely self-describing -- though the prompt is TRUNCATED to
about sixty characters in the filename, which is why `--from-post` exists: a
post that already carries these images has the FULL prompt in each alt.

EVERYTHING ARRIVES `staged`. Nothing is public until it is marked, exactly as
the essays worked. A Midjourney archive is mostly experiments and near
duplicates, and publishing a folder by accident is not a recoverable mistake
once someone has seen it.

RE-RUNNING NEVER CLOBBERS CURATION. status, title, tags and collection are
yours; this only ever fills in what is missing. That rule is here because the
post converter did not have it and silently reverted three published essays to
staged, discarding their summaries.
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
GALLERY = ROOT / "content" / "gallery"
IMAGES = GALLERY / "images"
INDEX = GALLERY / "index.json"

FULL_EDGE, THUMB_EDGE = 1600, 480
QUALITY, THUMB_QUALITY = 82, 74

CURATED = ("status", "title", "tags", "collection", "caption")

# `sdotmac_A_tranquil_scene_that_represents_30f016c2-f1e8-4de4-...`
MJ_NAME = re.compile(
    r"^(?P<user>[a-z0-9_.]+?)_(?P<prompt>.*?)_?"
    r"(?P<uuid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"(?:_(?P<variant>\d+))?$", re.I)

# Midjourney parameters are facts about the image, not description.
PARAMS = re.compile(r"--(\w+)(?:\s+(\S+))?")

# Words that carry no signal as a tag. Deliberately short: an over-eager stop
# list is how a tag vocabulary ends up missing the thing it was for.
STOP = set("""a an the and or of in on at to for with from by as is are was
were be been being this that these those it its their his her our your my
very really quite just more most some any all both each few other such only
own same so than too can will would should could into over under again
image picture photo shot render rendering style styled looking look very
highly detailed ultra realistic hyper 8k 4k hd resolution quality""".split())


def slugify(text, limit=60):
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:limit].rstrip("-") or "image"


def parse_name(stem):
    """A Midjourney filename -> (prompt, job uuid). Both may be None."""
    m = MJ_NAME.match(stem)
    if not m:
        return None, None
    prompt = m.group("prompt").replace("_", " ").strip()
    return (prompt or None), m.group("uuid")


def candidate_tags(prompt):
    """Words worth OFFERING as tags. Never applied without confirmation."""
    if not prompt:
        return []
    body = PARAMS.sub(" ", prompt.lower())
    words = re.findall(r"[a-z][a-z'-]{2,}", body)
    return [w for w in words if w not in STOP]


def parameters(prompt):
    """--ar 16:9, --v 6 and friends: facts, kept apart from the prose."""
    if not prompt:
        return {}
    return {k.lower(): (v or True) for k, v in PARAMS.findall(prompt)}


def optimise(src, dest_stem):
    """Write a full-size and a thumbnail WebP. Returns their metadata."""
    with Image.open(src) as im:
        im.load()
        alpha = im.mode in ("RGBA", "LA") and \
            im.convert("RGBA").getchannel("A").getextrema() != (255, 255)
        im = im.convert("RGBA" if alpha else "RGB")
        w, h = im.size

        full = im.copy()
        if max(w, h) > FULL_EDGE:
            s = FULL_EDGE / max(w, h)
            full = full.resize((round(w * s), round(h * s)), Image.LANCZOS)
        full_path = IMAGES / f"{dest_stem}.webp"
        full.save(full_path, "WEBP", quality=QUALITY, method=6)

        thumb = im.copy()
        s = THUMB_EDGE / max(thumb.size)
        if s < 1:
            thumb = thumb.resize((round(thumb.width * s), round(thumb.height * s)),
                                 Image.LANCZOS)
        thumb_path = IMAGES / f"{dest_stem}-t.webp"
        thumb.save(thumb_path, "WEBP", quality=THUMB_QUALITY, method=6)

    return {
        "file": full_path.name, "thumb": thumb_path.name,
        "width": full.width, "height": full.height,
        "aspect": round(full.width / full.height, 3),
        "bytes": full_path.stat().st_size + thumb_path.stat().st_size,
    }


def load_index():
    if INDEX.exists():
        return json.loads(INDEX.read_text(encoding="utf-8"))
    return {"images": []}


def from_post(slug):
    """Images and their FULL prompts out of an already-migrated post.

    The filename only ever holds a truncated prompt; a post that embeds these
    images holds the whole thing in each alt attribute. For the GameBoy series
    the filenames are content hashes from a Wayback rescue and carry nothing
    at all, so this is the only source.
    """
    md = ROOT / "content" / "posts" / slug / "index.md"
    if not md.exists():
        raise SystemExit(f"no such post: {slug}")
    text = md.read_text(encoding="utf-8")
    out = []
    for alt, rel in re.findall(r"!\[([^\]]*)\]\((media/[^)]+)\)", text):
        src = md.parent / rel
        if src.exists():
            out.append((src, alt.strip().strip('"')))
    for m in re.finditer(r'<img[^>]+src="(media/[^"]+)"[^>]*alt="([^"]*)"', text):
        src = md.parent / m.group(1)
        if src.exists():
            out.append((src, m.group(2).strip()))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder", nargs="?", help="a folder of image files")
    ap.add_argument("--from-post", action="append", default=[],
                    help="pull images and full prompts out of a migrated post")
    ap.add_argument("--collection", help="tag everything in this run as a series")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sources = []
    if args.folder:
        folder = Path(args.folder).expanduser()
        if not folder.is_dir():
            raise SystemExit(f"not a folder: {folder}")
        for p in sorted(folder.rglob("*")):
            if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                sources.append((p, None))
    for slug in args.from_post:
        sources.extend(from_post(slug))
    if not sources:
        raise SystemExit("nothing to ingest — give a folder or --from-post SLUG")

    index = load_index()
    by_key = {img["id"]: img for img in index["images"]}
    IMAGES.mkdir(parents=True, exist_ok=True)

    added, kept, tag_pool = 0, 0, Counter()
    for src, alt_prompt in sources:
        name_prompt, uuid = parse_name(src.stem)
        prompt = alt_prompt or name_prompt
        key = (uuid or hashlib.sha1(src.read_bytes()).hexdigest())[:12]

        if key in by_key:
            kept += 1
            tag_pool.update(candidate_tags(by_key[key].get("prompt")))
            continue

        stem = slugify(prompt or src.stem)
        if any(i["file"] == f"{stem}.webp" for i in index["images"]):
            stem = f"{stem}-{key[:6]}"

        if args.dry_run:
            added += 1
            continue

        meta = optimise(src, stem)
        entry = {
            "id": key,
            **meta,
            "prompt": prompt or "",
            "job_id": uuid,
            "source": str(src.relative_to(ROOT)) if src.is_relative_to(ROOT) else src.name,
            "parameters": parameters(prompt),
            # Curated fields. Nothing here is ever set by a later run.
            "status": "staged",
            "title": None,
            "tags": [],
            "collection": args.collection,
            "caption": None,
        }
        index["images"].append(entry)
        by_key[key] = entry
        tag_pool.update(candidate_tags(prompt))
        added += 1

    index["images"].sort(key=lambda i: (i.get("collection") or "", i["file"]))
    if not args.dry_run:
        INDEX.write_text(json.dumps(index, indent=2, ensure_ascii=False),
                         encoding="utf-8")

    total = len(index["images"])
    pub = sum(1 for i in index["images"] if i["status"] == "published")
    size = sum(i.get("bytes", 0) for i in index["images"]) / 1048576
    print(f"{added} new, {kept} already present")
    print(f"gallery: {total} images, {pub} published, {size:.1f} MiB")
    print(f"\ncandidate tags (yours to keep, rename or ignore):")
    for word, n in tag_pool.most_common(24):
        if n > 1:
            print(f"  {n:4}  {word}")
    if not args.dry_run:
        print(f"\n  -> {INDEX.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
