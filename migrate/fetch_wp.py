"""Capture seanmacrae.com to archive/ — the ONLY module that touches the network.

Bluehost is being cancelled. Once it is gone the source is gone, so this program
has one job: get untouched bytes onto disk, with a manifest, while the site is
still alive. It converts nothing. `convert.py` reads only archive/ and never the
network, which is what makes a conversion bug found three months after
cancellation still fixable.

THREE THINGS THAT WILL SILENTLY CORRUPT THIS CAPTURE IF YOU CHANGE THEM:

1. THE BROWSER USER-AGENT IS LOAD-BEARING. Bluehost's mod_security answers a
   non-browser UA with HTTP 406 and an HTML error body. `python-requests` gets
   406 on every request; `curl` gets 200. Without the header every download
   "succeeds" and you archive a directory of error pages that looks exactly like
   a successful run. `_check_not_error_page` is the second line of defence.

2. NEVER FETCH AN IMAGE THROUGH PHOTON. 260 of 266 <img src> in this site point
   at Jetpack's CDN (i0.wp.com). Those URLs carry `?resize=W,H`, a live
   downscale — the smallest in this corpus renders at 11x8 pixels. And Photon
   re-encodes even WITHOUT a resize parameter: one measured file serves 64,485
   bytes through Photon against 154,360 at origin. `un_photon()` runs on every
   URL before it is fetched, and verify.py asserts the result's dimensions
   against the media library's own width/height.

3. NO `_fields`. Capturing a subset bakes today's guess about what matters into
   the only copy that will ever exist. 12 posts of full JSON is under 1 MB.
   Filter at read time, in convert.py, where a mistake is reversible.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

SITE = "https://seanmacrae.com"
ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "archive"
MANIFEST = ARCHIVE / "MANIFEST.jsonl"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
DELAY = 0.5

# Measured 2026-09-22 against the live site. These are FLOORS, not expectations:
# `len(items) == X-WP-Total` passes happily when a suspended account returns
# X-WP-Total: 0 and an empty array. A hardcoded floor cannot.
FLOORS = {"posts": 12, "pages": 8, "media": 382, "categories": 10, "tags": 27}
# media: 382 exist, 335 are reachable via REST. See the note in api().
MEDIA_REACHABLE = 335

# PAGED collections answer with a JSON array and X-WP-Total headers.
COLLECTIONS = ["posts", "pages", "media", "categories", "tags", "comments", "users"]
# SINGLETONS answer with a JSON object and no paging. `types` is the one that
# matters: it is the proof that `portfolio` and `hb_testimonials` are not
# REST-registered, which is why 47 of their attachments cannot be enumerated.
SINGLETONS = ["types", "taxonomies", "statuses"]

# Hosts that are NOT seanmacrae.com and hold content we reference. Measured:
# cdn.midjourney.com, 15 images in explorations-in-gameboy-latent-space, all
# 403 at origin AND through Photon. They are already dead; Wayback is the only
# copy and it exists only under the PHOTON url.
EXTERNAL_RESCUE_HOSTS = {"cdn.midjourney.com"}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def un_photon(url):
    """https://i0.wp.com/host/path?resize=21%2C15&ssl=1 -> https://host/path

    Also drops the query string, which is where every Photon transform lives.
    Idempotent on a URL that was never Photoned.
    """
    m = re.match(r"^https?://i\d\.wp\.com/(.+)$", url)
    if m:
        url = "https://" + m.group(1)
    return url.split("?", 1)[0].split("#", 1)[0]


def _sha256(blob):
    return hashlib.sha256(blob).hexdigest()


def _check_not_error_page(url, resp):
    """mod_security answers a bad UA with 406 + text/html. Catch it loudly.

    Also catches the subtler case: a 200 whose body is an HTML error page where
    a binary was expected. A silently-archived error page is the failure this
    whole program exists to avoid.
    """
    if resp.status_code == 406:
        raise SystemExit(
            f"HTTP 406 from {url}\n"
            "  Bluehost's mod_security rejected the User-Agent. The browser UA "
            "header is load-bearing — see this module's docstring.")
    ctype = resp.headers.get("content-type", "")
    looks_binary = re.search(r"\.(png|jpe?g|gif|webp|mov|mp4|mp3|ogg|pdf)$",
                             urlparse(url).path, re.I)
    if looks_binary and "text/html" in ctype:
        raise SystemExit(
            f"{url}\n  returned text/html where an image/video was expected "
            f"({resp.status_code}, {len(resp.content)} bytes). This is an error "
            "page wearing a binary's filename. Refusing to archive it.")


class Capture:
    def __init__(self, force=False):
        self.force = force
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        ARCHIVE.mkdir(parents=True, exist_ok=True)
        self.seen = {}
        if MANIFEST.exists():
            for line in MANIFEST.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.seen[row["url"]] = row
        self.rows_added = 0
        self.drift = []

    def _record(self, url, path, resp, source, snapshot_ts=None):
        blob = resp.content
        sha = _sha256(blob)
        prev = self.seen.get(url)
        if prev and prev.get("sha256") != sha:
            self.drift.append((url, prev["sha256"][:12], sha[:12]))
        row = {
            "url": url,
            "path": str(path.relative_to(ARCHIVE)),
            "http_status": resp.status_code,
            "content_length": len(blob),
            "sha256": sha,
            "content_type": resp.headers.get("content-type", ""),
            "fetched_at": _now(),
            "source": source,
        }
        if snapshot_ts:
            row["snapshot_ts"] = snapshot_ts
        with MANIFEST.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        self.seen[url] = row
        self.rows_added += 1
        return row

    def get(self, url, path, source="origin", snapshot_ts=None, allow_404=False):
        """Fetch url to path verbatim. Returns the response, or None if skipped."""
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not self.force and url in self.seen:
            if _sha256(path.read_bytes()) == self.seen[url]["sha256"]:
                return None  # already captured, bytes agree
        time.sleep(DELAY)
        resp = self.session.get(url, timeout=60)
        if resp.status_code == 404 and allow_404:
            return resp
        _check_not_error_page(url, resp)
        resp.raise_for_status()
        path.write_bytes(resp.content)
        self._record(url, path, resp, source, snapshot_ts)
        return resp

    # ---------------------------------------------------------------- the API

    def api(self):
        out = ARCHIVE / "wp-api"
        out.mkdir(parents=True, exist_ok=True)
        self.get(f"{SITE}/wp-json/", out / "root.json")
        for name in SINGLETONS:
            self.get(f"{SITE}/wp-json/wp/v2/{name}", out / f"{name}.json")
        registered = sorted(json.loads(
            (out / "types.json").read_text(encoding="utf-8")).keys())
        print(f"  REST-registered types: {', '.join(registered)}")
        for absent in ("portfolio", "hb_testimonials"):
            assert absent not in registered, (
                f"{absent} IS REST-registered now — the 47-attachment gap needs "
                "re-diagnosing, because the explanation recorded in api() no "
                "longer holds.")
        totals = {"_rest_registered_types": registered}
        for name in COLLECTIONS:
            items, total, pages = [], None, 1
            page = 1
            while page <= pages:
                # NO _fields. See the module docstring.
                url = f"{SITE}/wp-json/wp/v2/{name}?per_page=100&page={page}"
                time.sleep(DELAY)
                resp = self.session.get(url, timeout=60)
                if resp.status_code == 400 and page > 1:
                    break
                _check_not_error_page(url, resp)
                resp.raise_for_status()
                if total is None:
                    total = int(resp.headers.get("X-WP-Total", 0))
                    pages = int(resp.headers.get("X-WP-TotalPages", 1)) or 1
                items.extend(resp.json())
                page += 1
            blob = json.dumps(items, indent=2, sort_keys=True).encode("utf-8")
            path = out / f"{name}.json"
            path.write_bytes(blob)
            totals[name] = {"got": len(items), "x_wp_total": total}

            # MEDIA IS THE ONE COLLECTION WHERE got != X-WP-Total LEGITIMATELY,
            # and the reason is worth writing down because it looks exactly like
            # a truncated capture. WordPress counts all 382 attachments in the
            # header, then filters the RESULT ROWS after the LIMIT is applied,
            # dropping any attachment whose post_parent is not publicly
            # readable. Measured 2026-09-22: pages return 61/100/92/82 = 335 for
            # per_page=100, and media_type image(364)+video(16)+audio(2) = 382.
            # The 47 hidden ones are attachments of the 2015 theme's `portfolio`
            # and `hb_testimonials` demo items, which are not REST-registered at
            # all — so REST can never enumerate them and no amount of paging
            # will. They are reached by the WXR export and the wget mirror.
            #
            # This is recorded, not swallowed: _totals.json carries the gap and
            # verify.py asserts that no CONTENT-REFERENCED file is among the
            # missing, which is the claim that actually matters.
            shortfall = (total or 0) - len(items)
            totals[name]["unreachable_via_rest"] = shortfall
            if name == "media":
                assert shortfall >= 0, f"media: got MORE than X-WP-Total ({shortfall})"
            else:
                assert len(items) == total, (
                    f"{name}: fetched {len(items)} but X-WP-Total says {total}")
            floor = FLOORS.get(name)
            if floor is not None:
                reachable_floor = floor if name != "media" else 335
                assert len(items) >= reachable_floor, (
                    f"{name}: got {len(items)}, floor is {reachable_floor} (measured "
                    f"2026-09-22). A suspended account returns 0 and passes the "
                    f"equality check above — this is the assertion that catches it.")
            gap = f"  [{shortfall} unreachable via REST]" if shortfall else ""
            print(f"  {name:12} {len(items):4}  (X-WP-Total {total}){gap}")
        (out / "_totals.json").write_text(
            json.dumps(totals, indent=2, sort_keys=True), encoding="utf-8")
        # A measured zero is an honest value; record it as measured.
        print(f"  comments are {totals['comments']['got']} — measured, not assumed")
        return totals

    # ------------------------------------------------------- rendered witness

    def posts(self):
        return json.loads((ARCHIVE / "wp-api" / "posts.json").read_text(encoding="utf-8"))

    def live_pages(self):
        out = ARCHIVE / "live-html"
        n = 0
        for p in self.posts():
            self.get(p["link"], out / f"{p['slug']}.html")
            n += 1
        pages = json.loads((ARCHIVE / "wp-api" / "pages.json").read_text(encoding="utf-8"))
        for p in pages:
            self.get(p["link"], out / f"page-{p['slug']}.html", allow_404=True)
            n += 1
        assert n >= FLOORS["posts"], f"only captured {n} live pages"
        print(f"  {n} rendered pages")

    def feed_and_sitemap(self):
        self.get(f"{SITE}/feed/", ARCHIVE / "feed" / "feed.xml")
        idx = ARCHIVE / "sitemap" / "wp-sitemap.xml"
        self.get(f"{SITE}/wp-sitemap.xml", idx)
        subs = re.findall(r"<loc>([^<]+)</loc>", idx.read_text(encoding="utf-8"))
        for u in subs:
            self.get(u, ARCHIVE / "sitemap" / Path(urlparse(u).path).name)
        print(f"  feed + {len(subs)} sitemaps")

    # ------------------------------------------------------------ the library

    def media(self):
        lib = json.loads((ARCHIVE / "wp-api" / "media.json").read_text(encoding="utf-8"))
        assert len(lib) >= MEDIA_REACHABLE, (
            f"media library enumerates only {len(lib)}; {MEDIA_REACHABLE} are "
            "reachable via REST (see the note in api())")
        ok = skipped = 0
        for m in lib:
            src = m.get("source_url")
            if not src:
                continue
            url = un_photon(src)            # never fetch through Photon
            rel = urlparse(url).path.split("/wp-content/uploads/", 1)
            rel = rel[1] if len(rel) == 2 else Path(urlparse(url).path).name
            path = ARCHIVE / "media-original" / unquote(rel)
            try:
                r = self.get(url, path)
                ok += 1 if r is not None else 0
                skipped += 1 if r is None else 0
            except requests.HTTPError as exc:
                print(f"  !! {url} -> {exc}")
        print(f"  {ok} downloaded, {skipped} already present, {len(lib)} in library")
        assert ok + skipped >= MEDIA_REACHABLE - 5, "too few media files captured"

    def qlcache(self):
        """The QuickLaTeX equation PNGs.

        These are NOT needed to convert the posts: every one carries its LaTeX
        source in its own alt attribute, and the converter recovers that
        instead, which is strictly better than a bitmap. They are captured
        anyway because they are the only evidence of what the rendered
        equations actually looked like, and the whole corpus is about 70 KB.

        They live in wp-content/ql-cache/ -- a PLUGIN CACHE, not the media
        library -- so nothing that enumerates /wp/v2/media will ever find them,
        and the wget mirror misses them too because every reference goes
        through Photon on another host.
        """
        urls = set()
        for post in self.posts():
            for src in re.findall(r'<img[^>]+src="([^"]+)"', post["content"]["rendered"]):
                u = un_photon(src.replace("&#038;", "&"))
                if "/ql-cache/" in u:
                    urls.add(u)
        print(f"  {len(urls)} distinct equation images")
        got = 0
        for u in sorted(urls):
            name = Path(urlparse(u).path).name
            try:
                self.get(u, ARCHIVE / "media-original" / "_qlcache" / name)
                got += 1
            except requests.HTTPError as exc:
                print(f"  !! {name}: {exc}")
        assert got >= len(urls) - 2, f"only captured {got} of {len(urls)} equation images"
        print(f"  {got} captured")

    # ----------------------------------------------- the dead external images

    def external_urls(self):
        """Every referenced image whose host is not ours. Measured: 15, all Midjourney."""
        urls = []
        for p in self.posts():
            for src in re.findall(r'<img[^>]+src="([^"]+)"', p["content"]["rendered"]):
                host = urlparse(un_photon(src)).netloc
                if host in EXTERNAL_RESCUE_HOSTS:
                    urls.append((p["slug"], src))          # keep the PHOTON url
        return urls

    def _wayback(self, url, want="20230601"):
        """Fetch url from the Wayback Machine, returning (bytes, timestamp).

        Deliberately does NOT use http://archive.org/wayback/available. That
        endpoint is rate-limited hard enough to 429 on the 15 requests this
        rescue needs, and it costs a second round trip per image. Requesting
        /web/<ts>im_/<url> directly makes Wayback resolve to the nearest
        snapshot itself and hand back the raw bytes; the timestamp it actually
        served comes back in the redirected URL.

        The `im_` suffix is what asks for the original bytes rather than a page
        with Wayback's navigation chrome injected into it.
        """
        snap = f"https://web.archive.org/web/{want}im_/{url}"
        delay = 3.0
        for attempt in range(6):
            time.sleep(delay)
            r = self.session.get(snap, timeout=120, allow_redirects=True)
            if r.status_code in (429, 503, 502):
                delay = min(delay * 2, 60)
                print(f"    {r.status_code} from Wayback, backing off {delay:.0f}s")
                continue
            if r.status_code == 404:
                return None, None
            r.raise_for_status()
            ts = None
            m = re.search(r"/web/(\d{14})", r.url)
            if m:
                ts = m.group(1)
            return r, ts
        raise SystemExit(
            f"Wayback kept rate-limiting {url} after 6 attempts. Wait and re-run "
            "`fetch_wp.py rescue` — it is idempotent and will skip what it has.")

    def rescue(self):
        """Pull the already-dead external images from the Wayback Machine.

        cdn.midjourney.com returns 403 at origin and through Photon; these
        images died some time before this migration began and are absent from
        every WXR export and every Bluehost backup. Wayback has them — but
        ONLY under the Photon URL. The origin URL has no snapshot. That
        distinction is the entire rescue, which is why this function is handed
        the Photon URL and must not un_photon it before querying.
        """
        targets = self.external_urls()
        print(f"  {len(targets)} external images referenced")
        out = ARCHIVE / "media-original" / "_external"
        out.mkdir(parents=True, exist_ok=True)
        idx_path = out / "_index.json"
        index = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else []
        have = {e["url"] for e in index}
        failed = []
        for slug, photon_url in targets:
            if photon_url in have and not self.force:
                continue
            key = hashlib.sha1(photon_url.encode()).hexdigest()
            ext = Path(urlparse(un_photon(photon_url)).path).suffix or ".png"
            path = out / f"{key}{ext}"
            r, ts = self._wayback(photon_url)
            if r is None:
                failed.append(photon_url)
                continue
            blob = r.content
            if not (blob.startswith(b"\x89PNG") or blob.startswith(b"\xff\xd8")
                    or blob[8:12] == b"WEBP"):
                failed.append(f"{photon_url}  (not an image: {blob[:16]!r})")
                continue
            path.write_bytes(blob)
            self._record(photon_url, path, r, "wayback", ts)
            index.append({"slug": slug, "url": photon_url, "path": path.name,
                          "source": "wayback", "snapshot_ts": ts, "bytes": len(blob)})
            have.add(photon_url)
            print(f"    ok {len(blob):>9,} B  {ts}  ...{photon_url[-44:]}")
            idx_path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
        idx_path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
        if failed:
            print("\n  NOT RESCUED — no Wayback snapshot:")
            for f in failed:
                print(f"    {f}")
            raise SystemExit(
                f"\n{len(failed)} external image(s) could not be rescued. They are "
                "gone from the origin AND from Wayback. Do not substitute a "
                "placeholder — decide what the post says about them instead.")
        assert len(have) >= len(targets), f"rescued {len(have)} of {len(targets)}"
        print(f"  {len(have)} of {len(targets)} rescued from Wayback")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("phase", nargs="?", default="all",
                    choices=["all", "api", "rescue", "pages", "feed", "media", "qlcache"])
    ap.add_argument("--force", action="store_true", help="re-download everything")
    args = ap.parse_args()

    cap = Capture(force=args.force)
    order = (["api", "rescue", "pages", "feed", "media", "qlcache"]
         if args.phase == "all" else [args.phase])
    for phase in order:
        print(f"\n== {phase} ==")
        getattr(cap, {"api": "api", "rescue": "rescue", "pages": "live_pages",
                      "feed": "feed_and_sitemap", "media": "media",
                      "qlcache": "qlcache"}[phase])()

    if cap.drift:
        print("\n!! CONTENT DRIFT since the last capture:")
        for url, before, after in cap.drift:
            print(f"   {before} -> {after}  {url}")
    print(f"\n{cap.rows_added} manifest rows added -> {MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
