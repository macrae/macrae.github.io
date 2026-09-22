# Migrating seanmacrae.com off WordPress

The record of what was found, what was decided, and where the archive lives.
Written as the work happened; every number here was measured, not estimated.

## Why this file exists

Bluehost is being cancelled. When it goes, the source goes — there is no
second copy of the WordPress database, the media library, or the theme. So the
migration is split in two, and the split is the whole design:

- **`fetch_wp.py` touches the network and converts nothing.** It writes
  untouched bytes to `archive/` with a manifest.
- **`convert.py` reads `archive/` and never the network.**

A conversion bug found three months after cancellation is therefore still
fixable. Conversion is a pure function of the capture, which also makes it
idempotent for free.

## What was actually on the site

| | count | note |
|---|---|---|
| posts | **12** | 2020-03-31 → 2025-03-05, **17,266 words total** |
| pages | 8 | **only `about` (143 words) is real** — 7 are dated 2015-03 |
| portfolio CPT | 9 | all 2015-03 |
| media library | 382 | of which **104 are referenced by the 12 posts** |
| comments | **0** | measured against `X-WP-Total`, not assumed |
| categories / tags | 10 / 27 | `Data Science` holds 7; every other holds 1 or 0 |

The 2015-dated pages, all 9 portfolio items and the `hb_testimonials` are the
theme's **demo content**, installed in 2015 and never removed.

Post URLs are flat — `https://seanmacrae.com/<slug>/` — which a static site
reproduces exactly as `<slug>/index.html`. **Permalinks are preserved with no
redirect machinery.**

## Five things that would have silently damaged the capture

Each was measured while writing the tool. Any one of them produces an archive
that looks complete and is not.

**1. The browser User-Agent is load-bearing.** Bluehost's mod_security answers
a non-browser UA with HTTP 406 and an HTML error body. `python-requests` gets
406 on every request. Without the header, every download "succeeds" and you
archive a directory of error pages. `-A "Mozilla/5.0"` is *also* rejected — the
bare string is a known bot signature — so the full Chrome UA is required.
`_check_not_error_page()` is the second line of defence: it refuses to archive
`text/html` under a binary's filename.

**2. Never fetch an image through Photon.** 260 of 266 `<img src>` point at
Jetpack's CDN (`i0.wp.com`). Those URLs carry `?resize=W,H`, a live downscale —
the smallest in this corpus renders at **11×8 pixels**. And Photon re-encodes
even *without* a resize parameter: one measured file serves **64,485 bytes**
through the CDN against **154,360 at origin**. `un_photon()` runs before every
fetch.

**3. The media library reports 382 and enumerates 335.** Not truncation.
WordPress counts every attachment in `X-WP-Total`, then filters result rows
*after* the LIMIT, dropping any whose `post_parent` is not publicly readable —
which is why pages return 61/100/92/82 for `per_page=100`. The 47 hidden ones
belong to the 2015 demo CPTs, and `/wp/v2/types` proves it: it lists neither
`portfolio` nor `hb_testimonials`, so REST can never enumerate their
attachments. That is now an **assertion** in `fetch_wp.api()`, so the
explanation cannot rot silently.

  **This was checked against the only thing that matters**: of the 104 upload
  files the 12 posts actually reference, **104 are present and 0 are missing**.
  The 47 invisible files are entirely demo content.

**4. 102 of the images are equations, and they are not in the media library.**
QuickLaTeX renders them to `wp-content/ql-cache/` — a *plugin cache*. Anything
enumerating `/wp/v2/media` misses every one and `kochs-snowflake` loses its
entire mathematical content. They are **losslessly recoverable**: each
`<img class="ql-img-inline-formula">` carries its LaTeX in the `alt`,
numeric-escaped — `&#32;&#65;&#95;&#123;&#110;&#125;&#32;` decodes to ` A_{n} `.
They come back as real LaTeX, which is a strict upgrade on the original.
147 occurrences, 102 distinct; all inline, `ql-img-displayed-formula` does not
occur anywhere in the corpus.

**5. Fifteen images were already dead before this migration began.**
`explorations-in-gameboy-latent-space` has **zero** files in the media library:
all 15 are hotlinked from `cdn.midjourney.com`, which now returns **403 at
origin and through Photon**. They are in no WXR export and no Bluehost backup —
cancelling the hosting has nothing to do with this loss. The Wayback Machine
has all 15, **but only under the Photon URL**; the origin URL has no snapshot.
That distinction is the entire rescue.

  All 15 recovered 2026-09-22 from the 2023-01-07 snapshot: 1024×1024 PNG,
  12.6 MiB total, every one decoded and dimension-checked. Their `alt`
  attributes hold the **Midjourney prompts**, which are content in their own
  right and must survive conversion.

## The content asset inventory

```
104  upload files referenced by the 12 posts   (all captured, 0 missing)
 15  Midjourney images                          (rescued from Wayback)
---
119  content assets total
102  QuickLaTeX equations -> recovered as LaTeX, NOT downloaded
231  library files unreferenced by any post     (demo content + orphans)
```

## Decisions, with what was rejected

| Decision | Rejected | Why |
|---|---|---|
| Capture full JSON, no `_fields` | Field filtering at capture | Bakes today's guess into the only copy that will ever exist. 12 posts of full JSON is under 1 MB. Filter at read time, where a mistake is reversible |
| Two programs, only one networked | One fetch-and-convert script | Shorter, and makes every post-cancellation bug unfixable |
| Equations → LaTeX from `alt` | Download 102 cache PNGs | The PNGs die with the site; the LaTeX is better than what was there |
| Wayback via `/web/<ts>im_/<url>` | The `availability` API | It 429s well inside the 15 requests this needs, and costs a second round trip per image |
| `status:` front-matter key | staging/ vs posts/ directories | A directory move rewrites every relative media path; a front-matter edit is a one-word diff |

## Where the archive lives

`archive/` is **gitignored** and must never be committed — this repository is
served by GitHub Pages, so anything in it is public and counts against the
budget. Git also gives nothing for immutable binary blobs, and Git LFS is ruled
out on the same grounds the sibling mana-map repo rules it out: Pages serves
LFS pointer files, not content.

The archive is a tarball plus `MANIFEST.sha256` in **two physical locations**.

- [ ] local copy: _record path_
- [ ] off-site copy: _record location_
- [ ] `MANIFEST.sha256` written and the copy verified against it

## Phase 0 status

- [x] 15 Midjourney images rescued from Wayback and dimension-checked
- [x] REST API captured — posts, pages, media, categories, tags, comments,
      users, types, taxonomies, statuses (385 manifest rows)
- [x] 20 rendered pages captured as a second witness
- [x] feed + 9 sitemaps captured
- [x] 335 media files captured from **origin**, never through Photon
- [x] all 104 content-referenced files verified present
- [ ] **WXR export** from `wp-admin → Tools → Export → All content` — the only
      source of raw `post_content`, because `?context=edit` returns 401. Needs
      a logged-in browser; cannot be scripted.
- [ ] **Full mirror** including `wp-content/ql-cache/`, with the browser UA
      (`brew install wget` first)
- [ ] archive duplicated to a second location and verified
