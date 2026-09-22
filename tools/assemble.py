"""Assemble dist/ — everything Cloudflare serves as a static asset.

    docs/                  ->  dist/
    ../mana-map/viz/       ->  dist/mana-map/viz/
    ../mana-map/manuals/   ->  dist/mana-map/manuals/
    ../mana-map/data/      ->  NOT HERE. Goes to R2 via tools/sync_r2.py.

WHY THE DATA IS SPLIT OFF, and why this exact layout.

Mana Map's JavaScript hardcodes `../data/<file>` in a dozen files, and its own
documentation calls that a hard constraint: viz/, data/ and manuals/ must stay
siblings. Two of those three are small enough to ship as assets; data/ is 238
MiB with a single file of 26.78 MiB, over Cloudflare's 25 MiB per-asset cap.

So data/ lives in R2 and a Worker serves it at `/mana-map/data/*` — the SAME
ORIGIN, at the SAME PATH the relative links already resolve to. From
`/mana-map/viz/index.html`, `../data/foo.json` is `/mana-map/data/foo.json`,
which the Worker answers from R2. Mana Map needs no code change at all, which
was the whole point of keeping the two repositories separate.
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
MANAMAP = ROOT.parent / "mana-map"

# Over Cloudflare's per-asset cap; anything at or above this must be in R2.
ASSET_MAX = 25 * 1024 * 1024


def copy_tree(src, dst, label):
    if not src.is_dir():
        raise SystemExit(f"{label}: {src} does not exist")
    n = 0
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = path.relative_to(src)
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, out)
        n += 1
    return n


def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    site = copy_tree(ROOT / "docs", DIST, "site")
    viz = copy_tree(MANAMAP / "viz", DIST / "mana-map" / "viz", "mana-map viz")
    man = copy_tree(MANAMAP / "manuals", DIST / "mana-map" / "manuals", "mana-map manuals")

    oversized = [(p, p.stat().st_size) for p in DIST.rglob("*")
                 if p.is_file() and p.stat().st_size >= ASSET_MAX]
    if oversized:
        print("FAIL: files at or over Cloudflare's 25 MiB asset cap:")
        for p, size in oversized:
            print(f"  {size/1048576:8.2f} MiB  {p.relative_to(DIST)}")
        return 1

    files = sum(1 for p in DIST.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
    print(f"dist/  {files} files, {size/1048576:.1f} MiB")
    print(f"  site            {site}")
    print(f"  mana-map/viz    {viz}")
    print(f"  mana-map/manuals{man:>4}")
    print(f"\n  mana-map/data   -> R2 (tools/sync_r2.py), served at /mana-map/data/*")
    if files > 20000:
        print(f"\nFAIL: {files} files exceeds the 20,000 free-plan asset limit")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
