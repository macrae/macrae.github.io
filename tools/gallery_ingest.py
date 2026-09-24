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
# The leading username is OPTIONAL. Discord downloads are
# `<user>_<prompt>_<uuid>`; web exports are `<prompt>_<uuid>_<variant>`, and
# requiring the prefix ate the first word of every prompt in this archive.
MJ_NAME = re.compile(
    r"^(?:(?P<user>[a-z0-9_.]+?)_)?(?P<prompt>.*?)_?"
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
highly detailed ultra realistic hyper 8k 4k hd resolution quality
like but has you not one medium long small large big new old many much
job https run httpss www com href url link using made make makes making
seen feel feels give gives set sets place places""".split())


def slugify(text, limit=60):
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:limit].rstrip("-") or "image"


def embedded(path):
    """Prompt, author and date out of the PNG's own metadata.

    Midjourney's exports carry tEXt chunks that are strictly better than the
    filename: the FULL prompt rather than ~60 truncated characters, the real
    creation date, and the author -- which is what proves a folder pulled from
    the Explore feed is your own work and not somebody else's.

    Measured on this archive: 2,416 of 2,416 files carry all three.
    """
    try:
        from PIL import Image
        with Image.open(path) as im:
            info = im.info
            size = im.size
    except Exception:
        return {}
    prompt = (info.get("Description") or "").strip()
    # "Job ID: <uuid>" is plumbing Midjourney appends to every Description.
    prompt = re.sub(r"\s*Job ID:.*$", "", prompt, flags=re.S | re.I).strip()
    # An image prompt is a URL given to Midjourney as an input. Real
    # provenance, so it is captured separately rather than deleted -- but it
    # is not prose and put `https` and `run` near the top of the tag
    # candidates 1,318 times each.
    urls = re.findall(r"(?:httpss?|https?)\S*s\.mj\.run/\S+|httpss?\S+", prompt, re.I)
    prompt = re.sub(r"(?:httpss?|https?)\S*s\.mj\.run/\S+|httpss?\S+", " ", prompt, flags=re.I)
    prompt = re.sub(r"\s{2,}", " ", prompt).strip(" ,;:")
    created = (info.get("Creation Time") or "").strip()
    iso = ""
    m = re.search(r"(\d{1,2})\s+(\w{3})\s+(20\d\d)", created)
    if m:
        months = {"Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05",
                  "Jun": "06", "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10",
                  "Nov": "11", "Dec": "12"}
        iso = f"{m.group(3)}-{months.get(m.group(2), '01')}-{int(m.group(1)):02d}"
    return {"prompt": prompt, "author": (info.get("Author") or "").strip(),
            "date": iso, "size": size, "image_prompts": urls}


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


def optimise(src, dest_stem, full=True):
    """Write a thumbnail, and the full size only when asked.

    A thumbnail is 13-21 KB and a full size is 123 KB, so generating full
    sizes for an entire archive costs 190 MiB of repository for images that
    may never be published. Thumbnails for everything (42 MiB) is what makes
    the archive browsable enough to curate; the full size is generated when an
    image is actually published.
    """
    with Image.open(src) as im:
        im.load()
        alpha = im.mode in ("RGBA", "LA") and \
            im.convert("RGBA").getchannel("A").getextrema() != (255, 255)
        im = im.convert("RGBA" if alpha else "RGB")
        w, h = im.size

        full_path = IMAGES / f"{dest_stem}.webp"
        out_w, out_h = w, h
        if full:
            big = im.copy()
            if max(w, h) > FULL_EDGE:
                sc = FULL_EDGE / max(w, h)
                big = big.resize((round(w * sc), round(h * sc)), Image.LANCZOS)
            big.save(full_path, "WEBP", quality=QUALITY, method=6)
            out_w, out_h = big.size

        thumb = im.copy()
        s = THUMB_EDGE / max(thumb.size)
        if s < 1:
            thumb = thumb.resize((round(thumb.width * s), round(thumb.height * s)),
                                 Image.LANCZOS)
        thumb_path = IMAGES / f"{dest_stem}-t.webp"
        thumb.save(thumb_path, "WEBP", quality=THUMB_QUALITY, method=6)

    return {
        "file": full_path.name, "thumb": thumb_path.name,
        "width": out_w, "height": out_h,
        "aspect": round(out_w / out_h, 3),
        "bytes": (full_path.stat().st_size if full_path.exists() else 0)
                 + thumb_path.stat().st_size,
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


def generate_full_sizes():
    """Make the full-size WebP for every published image that lacks one.

    Publishing is a one-word edit to index.json; this is what turns that word
    into a file. It reads the original from the path recorded at ingest, so
    the source archive has to still exist -- which is why ingest copies it
    somewhere permanent rather than trusting a Downloads folder.
    """
    index = load_index()
    made, missing = 0, []
    for img in index["images"]:
        if img.get("status") != "published":
            continue
        out = IMAGES / img["file"]
        if out.exists() and img.get("full_generated"):
            continue
        src = Path(img.get("source", ""))
        if not src.exists():
            missing.append((img["file"], str(src)))
            continue
        meta = optimise(src, Path(img["file"]).stem, full=True)
        img.update({k: meta[k] for k in ("width", "height", "aspect", "bytes")})
        img["full_generated"] = True
        made += 1
    INDEX.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"generated {made} full-size image(s)")
    for name, src in missing:
        print(f"  MISSING SOURCE for {name}: {src}")
    return 1 if missing else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder", nargs="?", help="a folder of image files")
    ap.add_argument("--from-post", action="append", default=[],
                    help="pull images and full prompts out of a migrated post")
    ap.add_argument("--collection", help="tag everything in this run as a series")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--publish-full", action="store_true",
                    help="generate full-size files for images marked published")
    args = ap.parse_args()

    if args.publish_full:
        return generate_full_sizes()

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
        emb = embedded(src)
        name_prompt, uuid = parse_name(src.stem)
        # PREFERENCE ORDER, best first: an alt from a post carries the full
        # prompt a human saw; the PNG's own metadata carries the full prompt
        # Midjourney recorded; the filename carries about sixty truncated
        # characters of it.
        prompt = alt_prompt or emb.get("prompt") or name_prompt
        variant = re.search(r"_(\d+)$", src.stem)
        # A job holds up to four DIFFERENT pictures, so the key must include
        # the variant or three of every four are silently discarded as
        # duplicates. Measured: 40 of 40 sampled jobs have distinct variants.
        base = uuid or hashlib.sha1(src.read_bytes()).hexdigest()
        key = f"{base[:12]}{'-' + variant.group(1) if variant else ''}"

        if key in by_key:
            kept += 1
            tag_pool.update(candidate_tags(by_key[key].get("prompt")))
            continue

        stem = slugify(PARAMS.sub(" ", prompt or src.stem))
        # THE SUFFIX MUST INCLUDE THE VARIANT. Using key[:8] took the first
        # eight characters of the job UUID, which is IDENTICAL for all four
        # variants of a job -- so four different pictures resolved to one
        # filename, overwrote each other, and 542 groups of images ended up
        # displaying whichever one was written last. Every count still
        # reconciled; only the files were wrong.
        if any(i["file"] == f"{stem}.webp" for i in index["images"]):
            stem = f"{stem}-{key}"

        if args.dry_run:
            added += 1
            continue

        # Thumbnail now, full size when it is published. See optimise().
        meta = optimise(src, stem, full=False)
        entry = {
            "id": key,
            **meta,
            "prompt": prompt or "",
            "job_id": uuid,
            "date": emb.get("date") or "",
            "image_prompts": emb.get("image_prompts") or [],
            "author": emb.get("author") or "",
            "source": str(src.resolve()),
            "full_generated": False,
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

    # TWO ENTRIES MUST NEVER CLAIM ONE FILE. This fired on 542 filenames the
    # first time this archive was ingested, and nothing else would have: the
    # counts were all correct, only the pictures were wrong.
    for field in ("file", "thumb"):
        seen = {}
        for img in index["images"]:
            if img[field] in seen:
                raise SystemExit(
                    f"two images claim {field} {img[field]!r}: "
                    f"{seen[img[field]]} and {img['id']}")
            seen[img[field]] = img["id"]

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
