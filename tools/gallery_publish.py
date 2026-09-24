"""Publish, stage or archive gallery images in bulk, by facet or by id.

Editing 2,431 JSON records by hand is not curation, it is data entry. This
selects with the same facets the gallery filters on, so what you see in
`make preview` is what you can act on:

    python tools/gallery_publish.py --subject goosebumps --year 2023 --dry-run
    python tools/gallery_publish.py --subject goosebumps --year 2023
    python tools/gallery_publish.py --id 8349beae-560-1 --id 841245a4-25e-0
    python tools/gallery_publish.py --subject horror --status archived

FILTERS COMBINE WITH AND, like the gallery panel across groups. --dry-run is
the default posture worth taking on a set this size: it prints what would
change and touches nothing.

Publishing generates the full-size file, because an image marked published
without one renders a broken <img>. That happens here rather than at build
time so the build stays hermetic.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from sitegen import facets                                        # noqa: E402
from gallery_ingest import INDEX, generate_full_sizes             # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--status", default="published",
                    choices=("published", "staged", "archived"))
    ap.add_argument("--id", action="append", default=[], help="exact image id")
    ap.add_argument("--collection")
    ap.add_argument("--year")
    ap.add_argument("--subject", action="append", default=[])
    ap.add_argument("--style", action="append", default=[])
    ap.add_argument("--material", action="append", default=[])
    ap.add_argument("--light", action="append", default=[])
    ap.add_argument("--condition", action="append", default=[])
    ap.add_argument("--orientation", choices=("square", "landscape", "portrait"))
    ap.add_argument("--limit", type=int, help="take only the first N matches")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(INDEX.read_text(encoding="utf-8"))
    images = data["images"]

    wanted = {k: v for k, v in (
        ("collection", [args.collection] if args.collection else []),
        ("year", [args.year] if args.year else []),
        ("orientation", [args.orientation] if args.orientation else []),
        ("subject", args.subject), ("style", args.style),
        ("material", args.material), ("light", args.light),
        ("condition", args.condition),
    ) if v}

    if not wanted and not args.id:
        ap.error("give at least one filter or --id, or everything matches")

    matched = []
    for img in images:
        if args.id:
            if img["id"] in args.id:
                matched.append(img)
            continue
        f = facets.for_image(img)
        # AND across groups, OR within one -- the same semantics the panel uses.
        if all(any(v in f.get(group, []) for v in values)
               for group, values in wanted.items()):
            matched.append(img)

    if args.limit:
        matched = matched[:args.limit]

    changing = [i for i in matched if i.get("status") != args.status]
    print(f"{len(matched)} matched, {len(changing)} would change to {args.status}")
    for img in changing[:12]:
        print(f"  {img.get('status','?'):10} -> {args.status:10} "
              f"{(img.get('title') or img.get('prompt') or '')[:60]}")
    if len(changing) > 12:
        print(f"  ... and {len(changing) - 12} more")

    if args.dry_run or not changing:
        if args.dry_run:
            print("\n--dry-run: nothing written")
        return 0

    for img in changing:
        img["status"] = args.status
    INDEX.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {len(changing)} change(s)")

    if args.status == "published":
        print("generating full-size files...")
        return generate_full_sizes()
    return 0


if __name__ == "__main__":
    sys.exit(main())
