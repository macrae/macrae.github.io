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
LOCK = threading.Lock()
STATUSES = ("published", "staged", "archived")


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
