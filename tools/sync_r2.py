"""Push mana-map's tracked data/ into R2, where the Worker serves it.

238 MiB across ~780 files, including one of 26.78 MiB that is over
Cloudflare's 25 MiB per-asset cap — which is the whole reason this is a bucket
rather than part of the deployed site.

Keys mirror the paths exactly: data/synergy_graph.json in the repo becomes the
key `synergy_graph.json`, which the Worker serves at
`/mana-map/data/synergy_graph.json`. That is the path mana-map's own
`../data/<file>` links already resolve to from /mana-map/viz/, so nothing in
that repository has to change.

Only TRACKED files are pushed. data/ on disk is 1.4 GB of regenerable
intermediates; git already knows which 238 MiB are the artifacts the site
actually serves.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANAMAP = ROOT.parent / "mana-map"
BUCKET = "seanmacrae-data"
STATE = ROOT / ".r2-state.json"
WRANGLER = ["npx", "--yes", "wrangler"]


def tracked_data_files():
    out = subprocess.run(["git", "ls-files", "-z", "data/"], cwd=MANAMAP,
                         capture_output=True, text=True, check=True).stdout
    return sorted(MANAMAP / p for p in out.split("\0") if p)


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def put(path, key):
    r = subprocess.run(
        WRANGLER + ["r2", "object", "put", f"{BUCKET}/{key}",
                    "--file", str(path), "--remote"],
        capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or r.stdout).strip().splitlines()[-1:] or [""]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--force", action="store_true", help="re-upload everything")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not MANAMAP.is_dir():
        raise SystemExit(f"mana-map not found at {MANAMAP}")

    files = tracked_data_files()
    assert len(files) >= 500, f"only {len(files)} tracked files under data/ — wrong repo?"

    state = json.loads(STATE.read_text()) if STATE.exists() and not args.force else {}
    todo = []
    for path in files:
        key = str(path.relative_to(MANAMAP / "data"))
        if state.get(key) == digest(path):
            continue
        todo.append((path, key))

    total = sum(p.stat().st_size for p, _ in todo)
    print(f"{len(files)} tracked files, {len(todo)} to upload "
          f"({total/1048576:.1f} MiB)")
    if args.dry_run or not todo:
        for p, k in todo[:10]:
            print(f"  {p.stat().st_size/1048576:8.2f} MiB  {k}")
        if len(todo) > 10:
            print(f"  ... and {len(todo) - 10} more")
        return 0

    done, failed = 0, []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(put, p, k): (p, k) for p, k in todo}
        for fut in futures:
            pass
        for fut, (p, k) in futures.items():
            ok, msg = fut.result()
            if ok:
                state[k] = digest(p)
                done += 1
                if done % 25 == 0:
                    print(f"  {done}/{len(todo)}")
            else:
                failed.append((k, msg))

    STATE.write_text(json.dumps(state, indent=0, sort_keys=True))
    print(f"\nuploaded {done}, failed {len(failed)}")
    for k, msg in failed[:10]:
        print(f"  FAIL {k}: {msg}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
