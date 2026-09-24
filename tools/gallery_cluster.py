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


def tfidf(docs, min_df=8, max_df=0.6):
    df = Counter()
    for d in docs:
        df.update(set(d))
    vocab = {w for w, n in df.items() if n >= min_df and n < len(docs) * max_df}
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


def lda(docs, vocab, k, iters=250, alpha=None, beta=0.01, seed=SEED):
    """Latent Dirichlet Allocation by collapsed Gibbs sampling.

    Chosen over k-means for one reason that matters here: MIXED MEMBERSHIP. A
    prompt like "a photorealistic airbrushed oil painting in the style of Tim
    Jacobus, a vertical book cover" is genuinely three topics at once, and
    k-means has to pick one and throw the rest away. A facet is exactly the
    place where an image should be allowed to belong to several things.

    Pure Python. ~70k tokens over 12 topics for 250 sweeps is a few minutes,
    which is fine for something run by hand and committed afterwards.

    Deterministic: seeded, fixed sweeps. This writes into a committed file.
    """
    rng = random.Random(seed)
    index = {w: i for i, w in enumerate(vocab)}
    corpus = [[index[w] for w in d if w in index] for d in docs]
    V, D = len(vocab), len(corpus)
    alpha = alpha if alpha is not None else 50.0 / k

    nd = [[0] * k for _ in range(D)]          # doc -> topic counts
    nw = [[0] * V for _ in range(k)]          # topic -> word counts
    nk = [0] * k                              # topic totals
    z = []
    for d, doc in enumerate(corpus):
        zs = []
        for w in doc:
            t = rng.randrange(k)
            zs.append(t)
            nd[d][t] += 1
            nw[t][w] += 1
            nk[t] += 1
        z.append(zs)

    vbeta = V * beta
    for sweep in range(iters):
        for d, doc in enumerate(corpus):
            ndd = nd[d]
            for i, w in enumerate(doc):
                t = z[d][i]
                ndd[t] -= 1; nw[t][w] -= 1; nk[t] -= 1
                total, probs = 0.0, [0.0] * k
                for tt in range(k):
                    pr = (ndd[tt] + alpha) * (nw[tt][w] + beta) / (nk[tt] + vbeta)
                    probs[tt] = pr
                    total += pr
                r, acc, new = rng.random() * total, 0.0, k - 1
                for tt in range(k):
                    acc += probs[tt]
                    if acc >= r:
                        new = tt
                        break
                z[d][i] = new
                ndd[new] += 1; nw[new][w] += 1; nk[new] += 1
        if sweep and sweep % 50 == 0:
            print(f"    sweep {sweep}/{iters}")

    # theta: per-document topic mixture; phi: per-topic word distribution
    theta = [[(nd[d][t] + alpha) / (len(corpus[d]) + k * alpha) if corpus[d] else 0.0
              for t in range(k)] for d in range(D)]
    phi = [[(nw[t][w] + beta) / (nk[t] + vbeta) for w in range(V)] for t in range(k)]
    return theta, phi


def topic_labels(phi, vocab, n=3):
    """Name a topic by the words it puts the most mass on."""
    out = []
    for row in phi:
        top = sorted(range(len(vocab)), key=lambda w: -row[w])[:n]
        out.append("-".join(vocab[w] for w in top))
    return out


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
    # DEFAULT IS K-MEANS, AND IT WAS MEASURED RATHER THAN ASSUMED.
    #
    # LDA is the better-fitting model on paper -- a prompt really is several
    # topics at once, and mixed membership is what a facet wants. It was
    # implemented, run twice, and lost both times on this corpus:
    #
    #   k-means  x-men 449, frazetta-fantasy 303, goosebumps 248,
    #            landscapes 220, coloring-pages 150, star-wars 130
    #   LDA      cinematic-comiccore-pop 585, sword-girl-lavender 375,
    #            streets-around-metal 361, sense-mallard-frank 290
    #
    # My first explanation was that shared style boilerplate dominated LDA's
    # topics while idf suppressed it for k-means. That was WRONG, and the
    # measurement says so: tightening max_df from 0.6 to 0.10 changed the
    # vocabulary by fourteen terms, 2,254 to 2,240, and the topics stayed
    # just as vague.
    #
    # The real reason is document length. The median prompt is SIXTEEN tokens
    # and 828 of 2,342 have fewer than ten usable ones. LDA infers a per
    # document topic MIXTURE from the tokens in that document, and sixteen
    # tokens is not enough evidence for a mixture. TF-IDF never needs to: it
    # compares whole weighted vectors and puts enormous weight on rare
    # distinctive terms -- wolverine, frazetta, goosebumps -- which is exactly
    # what makes a theme recognisable to a person.
    #
    # Keep both. On a corpus of longer prompts LDA would likely win, and the
    # `themes` list it writes is read by the facet layer already.
    ap.add_argument("--method", choices=("lda", "kmeans"), default="kmeans",
                    help="lda allows an image in several themes; measured "
                         "worse here, see the note above")
    ap.add_argument("--max-df", type=float, default=0.6,
                    help="drop terms appearing in more than this share of "
                         "prompts; LDA needs this tighter than k-means because "
                         "it has no idf to suppress boilerplate")
    ap.add_argument("--min-weight", type=float, default=0.18,
                    help="lda: least share of a prompt a topic needs to count")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = json.loads(INDEX.read_text(encoding="utf-8"))
    images = [i for i in data["images"] if i.get("status") != "archived"]
    if len(images) < args.k * 5:
        raise SystemExit(f"only {len(images)} images: too few for {args.k} themes")

    docs = docs_of(images)
    vectors, vocab = tfidf(docs, max_df=args.max_df)
    print(f"{len(images)} prompts, {len(vocab)} terms kept "
          f"({args.method})\n")

    if args.method == "lda":
        theta, phi = lda(docs, vocab, args.k)
        names = {c: n for c, n in enumerate(topic_labels(phi, vocab))}
        seen = Counter()
        for c in range(args.k):
            seen[names[c]] += 1
            if seen[names[c]] > 1:
                names[c] = f"{names[c]}-{seen[names[c]]}"
        # MIXED MEMBERSHIP: every topic holding a real share of a prompt, not
        # just the largest. That is the whole reason for choosing LDA.
        themes = []
        for row in theta:
            picked = [names[c] for c in range(args.k) if row[c] >= args.min_weight]
            if not picked and any(row):
                picked = [names[max(range(args.k), key=lambda c: row[c])]]
            themes.append(sorted(picked))
        sizes = Counter(t for ts in themes for t in ts)
        for name, n in sizes.most_common():
            c = next(c for c in names if names[c] == name)
            print(f"  {n:5}  {name}")
            for img, ts in zip(images, themes):
                if ts and ts[0] == name:
                    print(f"         {(img.get('prompt') or '')[:72]}")
                    break
        multi = sum(1 for t in themes if len(t) > 1)
        print(f"\n  {multi} of {len(themes)} prompts sit in more than one theme")
        if args.dry_run:
            print("\n--dry-run: nothing written")
            return 0
        for img, ts in zip(images, themes):
            img["themes"] = ts
            img.pop("theme", None)
        INDEX.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                         encoding="utf-8")
        print(f"\nwrote `themes` onto {len(images)} images")
        return 0

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
