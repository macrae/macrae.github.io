"""A LOCAL curation server. Never deployed, and the site cannot depend on it.

Serves the preview build and adds one write endpoint, so archiving an image is
a click rather than an edit to a 2,431-entry JSON file.

    python tools/curate.py          # http://localhost:8091/gallery/

THE DEPLOYED SITE HAS NO /curate. gallery.js probes for it once and only shows
the archive buttons when the probe succeeds, exactly as the sibling mana-map
repo gates its own local API: the affordance is ABSENT in production, not
broken. A visitor can never see a control that would write to your disk.

Writes go straight to content/gallery/index.json, so a decision survives the
next build, the next ingest and everything else -- it is in git the moment you
commit.
"""

import json
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
PREVIEW = ROOT / "preview"
INDEX = ROOT / "content" / "gallery" / "index.json"
IMAGES = ROOT / "content" / "gallery" / "images"
LOCK = threading.Lock()
STATUSES = ("published", "staged", "archived")

ARCHIVED_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Archived</title><style>
*{box-sizing:border-box}body{margin:0;background:#14130f;color:#efe9dd;
font:15px/1.5 ui-sans-serif,-apple-system,system-ui,sans-serif;padding:2rem 1.5rem 5rem}
h1{font:600 1.6rem/1.2 ui-serif,Georgia,serif;margin:0 0 .2rem}
p.sub{color:#8b8474;margin:0 0 2rem}
a{color:#e0937c}
.grid{display:grid;gap:1.2rem;grid-template-columns:repeat(auto-fill,minmax(230px,1fr))}
figure{margin:0;background:#1b1914;border:1px solid #2a261f;border-radius:4px;
padding:.7rem;display:flex;flex-direction:column;gap:.55rem}
img{width:100%%;height:auto;border-radius:2px;opacity:.75}
figure:hover img{opacity:1}
figcaption{font-size:.76rem;line-height:1.45;color:#a9a294;flex:1}
figcaption small{color:#6f6a5e}
button{background:#2f4858;color:#fff;border:0;border-radius:3px;padding:.45rem;
cursor:pointer;font-size:.8rem}
button:hover{background:#3f6b3f}
button[disabled]{background:#3a352c;cursor:default}
figure.gone{opacity:.35}
</style></head><body>
<h1>Archived</h1>
<p class="sub">%d images, newest first. Nothing here is deleted &mdash; they are
in <code>content/gallery/index.json</code> and in git. Restoring puts one back
as <code>staged</code>. <a href="/gallery/">back to the gallery</a></p>
<div class="grid">%s</div>
<script>
document.addEventListener("click", function (ev) {
  var b = ev.target.closest("button[data-id]");
  if (!b) return;
  b.disabled = true; b.textContent = "Restoring\u2026";
  fetch("/curate/status", {method:"POST",
    headers:{"content-type":"application/json"},
    body: JSON.stringify({ids:[b.dataset.id], status:"staged"})})
   .then(function(r){return r.json();})
   .then(function(res){
     if (!res.ok) { b.disabled = false; b.textContent = "Restore"; return; }
     b.textContent = "Restored";
     b.closest("figure").classList.add("gone");
   });
});
</script></body></html>"""


def _load():
    return json.loads(INDEX.read_text(encoding="utf-8"))


class Handler(SimpleHTTPRequestHandler):
    def _json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/curate/thumb/"):
            # STRAIGHT FROM content/gallery/images/, not from the preview
            # build. The build deliberately does not copy archived images --
            # they are not part of the site -- so the archived view could only
            # show the handful archived since the last rebuild and the rest
            # came up blank. Every thumbnail exists; the served tree just did
            # not have them.
            name = unquote(self.path.rsplit("/", 1)[-1].split("?")[0])
            src = IMAGES / name
            # Refuse anything that climbs out of the image directory.
            if ".." in name or "/" in name or not src.exists():
                return self._json({"error": "no such image"}, 404)
            blob = src.read_bytes()
            self.send_response(200)
            self.send_header("content-type", "image/webp")
            self.send_header("content-length", str(len(blob)))
            self.send_header("cache-control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(blob)
            return
        if self.path.startswith("/curate/original/"):
            # THE ORIGINAL, STRAIGHT OFF THE ARCHIVE. A staged image has only
            # a 480px thumbnail in the repository, because generating full
            # sizes for 2,400 pictures that may never be published would cost
            # 190 MiB of git. But judging an image at 480px is guesswork, so
            # while curating the lightbox gets the real file from
            # archive/gallery-source/ -- local only, zero repository cost, and
            # absent in production exactly like the archive button.
            key = unquote(self.path.rsplit("/", 1)[-1].split("?")[0])
            with LOCK:
                img = next((i for i in _load()["images"] if i["id"] == key), None)
            if not img:
                return self._json({"error": "unknown id"}, 404)
            src = Path(img.get("source", ""))
            if not src.exists():
                return self._json({"error": "source not in the archive"}, 404)
            blob = src.read_bytes()
            self.send_response(200)
            self.send_header("content-type", "image/png")
            self.send_header("content-length", str(len(blob)))
            self.send_header("cache-control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(blob)
            return
        if self.path.startswith("/curate/archived"):
            # NOTHING IS DELETED. Archiving sets a word in a JSON file, so a
            # change of mind costs one click -- but only if you can SEE what
            # you archived, and the gallery build deliberately leaves those
            # images out. This is that view.
            with LOCK:
                data = _load()
            arch = [i for i in data["images"] if i["status"] == "archived"]
            arch.sort(key=lambda i: (i.get("date") or "", i["file"]), reverse=True)
            tiles = "".join(
                '<figure data-id="%s"><img src="/curate/thumb/%s" alt="" '
                'loading="lazy"><figcaption>%s<br><small>%s</small></figcaption>'
                '<button data-id="%s">Restore</button></figure>' % (
                    i["id"], i["thumb"],
                    (i.get("prompt") or "")[:150].replace("<", "&lt;"),
                    i.get("date") or "", i["id"])
                for i in arch)
            page = ARCHIVED_PAGE % (len(arch), tiles)
            body = page.encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/curate/statuses"):
            # THE PAGE IS A STATIC BUILD AND THE DECISIONS ARE NOT. Archiving
            # writes to index.json immediately, but the rendered HTML still
            # holds every tile it had when it was built -- so a refresh
            # brought archived images back and looked exactly like the work
            # had been lost. It had not: it was in the file the whole time.
            # The client asks for the current statuses on load and drops what
            # has gone, instead of rebuilding 2,400 pages after every click.
            with LOCK:
                data = _load()
            return self._json({i["id"]: i["status"] for i in data["images"]})
        if self.path.startswith("/curate/health"):
            with LOCK:
                data = _load()
            counts = {}
            for img in data["images"]:
                counts[img["status"]] = counts.get(img["status"], 0) + 1
            return self._json({"ok": True, "counts": counts})
        return super().do_GET()

    def do_POST(self):
        if not self.path.startswith("/curate/status"):
            return self._json({"error": "unknown endpoint"}, 404)
        try:
            n = int(self.headers.get("content-length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception as exc:
            return self._json({"error": f"bad request: {exc}"}, 400)

        ids, status = req.get("ids") or [], req.get("status")
        if status not in STATUSES:
            return self._json({"error": f"status must be one of {STATUSES}"}, 400)
        if not ids:
            return self._json({"error": "no ids"}, 400)

        with LOCK:
            data = _load()
            by_id = {i["id"]: i for i in data["images"]}
            missing = [i for i in ids if i not in by_id]
            if missing:
                return self._json({"error": f"unknown ids: {missing[:3]}"}, 404)
            for i in ids:
                by_id[i]["status"] = status
            # Written whole and atomically: a half-written index would lose
            # curation decisions that exist nowhere else.
            tmp = INDEX.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                           encoding="utf-8")
            tmp.replace(INDEX)
            counts = {}
            for img in data["images"]:
                counts[img["status"]] = counts.get(img["status"], 0) + 1
        print(f"  {len(ids)} -> {status}   {counts}")
        return self._json({"ok": True, "changed": len(ids), "counts": counts})

    def log_message(self, *args):
        pass          # the POST handler prints what matters


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8091
    if not (PREVIEW / "gallery" / "index.html").exists():
        raise SystemExit("no preview build — run:  make preview")
    handler = partial(Handler, directory=str(PREVIEW))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    with LOCK:
        counts = {}
        for img in _load()["images"]:
            counts[img["status"]] = counts.get(img["status"], 0) + 1
    print(f"curating {sum(counts.values())} images  {counts}")
    print(f"\n  http://localhost:{port}/gallery/\n")
    print("  X archives an image (hidden from the site, kept in git)")
    print("  writes go to content/gallery/index.json immediately")
    print("  ctrl-c to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
