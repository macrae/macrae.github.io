# Deploying

The site is a committed folder of static files. Cloudflare serves it, a Worker
handles the three things a static file cannot.

```
seanmacrae.com ──► Worker
   ├─ /                    static assets   (docs/ + mana-map viz & handbooks)
   ├─ /api/*        ──► D1  the queryable data behind the visualisations
   ├─ /admin        ──► GitHub Contents API, behind Cloudflare Access
   └─ /mana-map/data/*        237 MiB of artifacts, as ordinary assets
```

## Why the R2 route is shaped like that

Mana Map's JavaScript hardcodes `../data/<file>` in a dozen files, and that
repo's own docs call it a hard constraint: `viz/`, `data/` and `manuals/` must
stay siblings. Serving R2 at `/mana-map/data/*` — the same origin, the exact
path those links already resolve to from `/mana-map/viz/` — means the whole
workbench changes hosts **without one line of it changing**.

`data/` ships as ordinary static assets. Exactly one file is over
Cloudflare's 25 MiB per-asset cap — `synergy_graph.json` at 26.78 MiB — so
`tools/assemble.py` stores that one gzipped and the Worker decompresses it on
the way out.

Serving the `.gz` with `content-encoding: gzip` does **not** work here: the
Workers runtime manages encoding itself and strips that header, so the browser
receives gzip bytes labelled as JSON and fails. `DecompressionStream` is used
instead — native and streaming, so it neither buffers 26 MiB nor spends the
10 ms CPU budget — and Cloudflare re-compresses on the way out. Measured: the
reader receives **1.44 MiB** (brotli) for a 26.78 MiB file, 19x smaller than
the original and better than the gzip we stored.

**R2 is not needed and is not used.** It would be the better answer if this
outgrew the asset limits — it syncs only what changed rather than re-uploading
— but it requires a payment method on the account, which 217 MiB does not
justify. `tools/sync_r2.py` and the Worker's R2 path are kept for that day.

## First-time setup

```bash
npx wrangler login                                   # opens a browser
npx wrangler d1 create seanmacrae                    # paste the id into wrangler.toml
make db

# A fine-grained GitHub PAT, Contents: read/write, this repo only:
npx wrangler secret put GITHUB_TOKEN

make deploy
```

Then, to protect `/admin`: create a Cloudflare Access application for
`seanmacrae.com/admin*`, and set `ACCESS_TEAM` and `ACCESS_AUD` in
`wrangler.toml` from it. **Until both are set, `/admin` refuses every
request** — it fails closed rather than standing open, which is the one
failure this codebase could not afford.

## Analytics, and why there is still no JavaScript

Cloudflare gives per-path request analytics in the dashboard for any proxied
domain, **with no client-side code at all**. That is what this uses, because
it keeps the site's no-script guarantee intact.

Cloudflare Web Analytics (bounce rate, referrers, Core Web Vitals) needs a
beacon script. It is a real trade and not an obvious one: adding it means every
page carries JavaScript for the first time. If you want it, declare it
deliberately rather than pasting a snippet into the template.

## Day to day

```bash
make check      # build, validate, test — before any push
make deploy     # assemble and ship
```

Writing a post: edit `content/posts/<slug>/index.md` and `make deploy`. Or use
`/admin` from any browser — it commits to this repo through the GitHub API
under your Access identity, and the normal build deploys the result. You never
make the commit; you still get the history.

## The cutover, in order

1. Move DNS for `seanmacrae.com` to Cloudflare (nameserver change at Bluehost).
2. Add the Worker route for the domain and check the site serves.
3. Set `CUSTOM_DOMAIN_LIVE = True` in `src/sitegen/spec.py`, `make deploy`.
4. **Drop the MX record.** Irreversible for mail.
5. **Cancel Bluehost.** Irreversible for everything.

Do not reorder. Steps 4 and 5 are the only ones that cannot be undone.
