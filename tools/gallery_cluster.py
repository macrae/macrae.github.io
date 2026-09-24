"""Cluster the prompts into themes, so the panel has a few real groups.

Eleven facet groups and sixty-four pills is a filing cabinet, not a filter.
The lexicon facets were hand-written and each one is a guess I had to justify;
this instead asks the prompts what they are about.

TF-IDF over the prompt text, L2-normalised, then spherical k-means (cosine
similarity) in pure Python. 2,342 documents over ~1,000 meaningful terms is
small enough that numpy would be a dependency bought for nothing.

DETERMINISTIC BY CONSTRUCTION. k-means++ seeded from a fixed constant and a
fixed iteration count, so the same prompts always produce the same themes --
this writes into content/gallery/index.json, which is committed, and a
clustering that drifted between runs would churn the diff every time anyone
touched it.

THE NAMES ARE A STARTING POINT, NOT AN ANSWER. Each cluster is labelled with
the terms that distinguish it from the rest of the corpus, which is honest but
rarely graceful. Rename them in index.json; nothing recomputes them unless you
re-run this.
"""

import argparse
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "content" / "gallery" / "index.json"
SEED = 20260923

PARAMS = re.compile(r"--\w+(?:\s+\S+)?")
STOP = set("""the and of in on at to for with from by as is are was were be been
being this that these those it its their his her our your my a an one two very
really quite just more most some any all both each few other such only own same
so than too can will would should could into over under again not no yes but
like has have had who what when where which while there here them they he she
you we us i me him style styled image picture photo shot render rendering
detailed ultra hyper resolution quality highly realistic looking look made make
creating create scene view background foreground featuring feature shows show
single full half close wide long short small large big new old
""".split())


def docs_of(images):
    out = []
    for img in images:
        text = PARAMS.sub(" ", (img.get("prompt") or "").lower())
        words = [w for w in re.findall(r"[a-z][a-z-]{2,}", text) if w not in STOP]
        out.append(words)
    return out


def tfidf(docs, min_df=8):
    df = Counter()
    for d in docs:
        df.update(set(d))
    vocab = {w for w, n in df.items() if n >= min_df and n < len(docs) * 0.6}
    n = len(docs)
    idf = {w: math.log(n / df[w]) for w in vocab}
    vectors = []
    for d in docs:
        tf = Counter(w for w in d if w in vocab)
        vec = {w: (1 + math.log(c)) * idf[w] for w, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vectors.append({w: v / norm for w, v in vec.items()})
    return vectors, sorted(vocab)


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(w, 0.0) for w, v in a.items())


def kmeans(vectors, k, iters=25, seed=SEED):
    rng = random.Random(seed)
    live = [i for i, v in enumerate(vectors) if v]
    if len(live) <= k:
        return {i: 0 for i in range(len(vectors))}, [{}] * k

    # k-means++ so the starting points are spread, seeded so they are the same
    # spread every time.
    centres = [dict(vectors[rng.choice(live)])]
    while len(centres) < k:
        d2 = []
        for i in live:
            best = max((cosine(vectors[i], c) for c in centres), default=0.0)
            d2.append(max(0.0, 1.0 - best) ** 2)
        total = sum(d2) or 1.0
        r, acc = rng.random() * total, 0.0
        pick = live[-1]
        for i, w in zip(live, d2):
            acc += w
            if acc >= r:
                pick = i
                break
        centres.append(dict(vectors[pick]))

    assign = {}
    for _ in range(iters):
        groups = defaultdict(list)
        for i in live:
            best, score = 0, -1.0
            for c, centre in enumerate(centres):
                s = cosine(vectors[i], centre)
                if s > score:
                    best, score = c, s
            assign[i] = best
            groups[best].append(i)
        new = []
        for c in range(k):
            members = groups.get(c) or []
            if not members:
                new.append(centres[c])
                continue
            acc = defaultdict(float)
            for i in members:
                for w, v in vectors[i].items():
                    acc[w] += v
            norm = math.sqrt(sum(v * v for v in acc.values())) or 1.0
            # Keep the heaviest terms: a full centroid is mostly noise and
            # makes every comparison slower for nothing.
            top = sorted(acc.items(), key=lambda kv: -kv[1])[:200]
            new.append({w: v / norm for w, v in top})
        centres = new
    return assign, centres


def label(centre, others, n=3):
    """Terms that distinguish this cluster from the average of the rest."""
    rest = defaultdict(float)
    for o in others:
        for w, v in o.items():
            rest[w] += v
    m = max(1, len(others))
    scored = sorted(((v - rest.get(w, 0.0) / m, w) for w, v in centre.items()),
                    reverse=True)
    return [w for _, w in scored[:n]]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-k", type=int, default=12, help="how many themes")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(INDEX.read_text(encoding="utf-8"))
    images = [i for i in data["images"] if i.get("status") != "archived"]
    if len(images) < args.k * 5:
        raise SystemExit(f"only {len(images)} images: too few for {args.k} themes")

    vectors, vocab = tfidf(docs_of(images))
    print(f"{len(images)} prompts, {len(vocab)} terms kept\n")
    assign, centres = kmeans(vectors, args.k)

    names, sizes = {}, Counter(assign.values())
    for c in range(args.k):
        others = [centres[o] for o in range(args.k) if o != c]
        names[c] = "-".join(label(centres[c], others)) or f"theme-{c}"

    seen = Counter()
    for c in range(args.k):
        seen[names[c]] += 1
        if seen[names[c]] > 1:
            names[c] = f"{names[c]}-{seen[names[c]]}"

    for c in sorted(range(args.k), key=lambda c: -sizes[c]):
        print(f"  {sizes[c]:5}  {names[c]}")
        sample = [images[i] for i in assign if assign[i] == c][:2]
        for s in sample:
            print(f"         {(s.get('prompt') or '')[:74]}")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0

    for n, img in enumerate(images):
        img["theme"] = names.get(assign.get(n), "unsorted")
    INDEX.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote `theme` onto {len(images)} images -> {INDEX.relative_to(ROOT)}")
    print("Rename any of them in index.json; nothing recomputes unless you re-run this.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
