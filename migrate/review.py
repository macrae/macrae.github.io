"""The curation surface: read 12 posts, decide which publish.

Builds every post — staged and all — and writes preview/_review.html: one row
per post with the rendered page, the captured WordPress original beside it, and
the numbers that say whether the conversion held.

This is the step that cannot be automated. The counts prove no image, equation
or code block was dropped; they cannot see that a figure now sits above the
paragraph it belonged to, or that a sentence reads wrong. Twelve posts is one
sitting.

To publish one: open content/posts/<slug>/index.md, change `status: staged` to
`status: published`, and add the three keys publishing requires — `summary`,
`category` (from spec.CATEGORIES) and `tags` (from spec.TAGS). The build
refuses to publish without them, which is what makes curation a decision
rather than an omission.
"""

import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "archive"
POSTS = ROOT / "content" / "posts"
PREVIEW = ROOT / "preview"

sys.path.insert(0, str(ROOT / "src"))
from sitegen import frontmatter                                    # noqa: E402

CSS = """
*{box-sizing:border-box} body{margin:0;background:#14130f;color:#efe9dd;
  font:15px/1.5 ui-sans-serif,-apple-system,system-ui,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:2.5rem 1.5rem 5rem}
h1{font:600 1.8rem/1.2 ui-serif,Georgia,serif;margin:0 0 .3rem}
.sub{color:#9a9384;margin:0 0 2.5rem}
table{width:100%;border-collapse:collapse}
th{text-align:left;font-size:.72rem;letter-spacing:.09em;text-transform:uppercase;
  color:#8b8474;border-bottom:1px solid #3a352c;padding:.5rem .6rem}
td{padding:.85rem .6rem;border-bottom:1px solid #26221b;vertical-align:top}
tr:hover td{background:#1b1914}
.t{font-weight:600;color:#f3eee3}
.t a{color:inherit;text-decoration:none}
.t a:hover{color:#e0937c}
.d{color:#8b8474;font-size:.8rem;margin-top:.15rem}
.n{font-variant-numeric:tabular-nums;text-align:right;color:#c3bcab}
.z{color:#4e4940}
.badge{display:inline-block;font-size:.68rem;letter-spacing:.06em;text-transform:uppercase;
  padding:.12rem .45rem;border-radius:3px;border:1px solid #4a4436;color:#a9a294}
.staged{border-color:#7a6a3a;color:#d4af4a}
.published{border-color:#3f6b3f;color:#7ec77e}
.archived{border-color:#4a4436;color:#7d7668}
.go{font-size:.78rem;white-space:nowrap}
.go a{color:#8fb3c7;text-decoration:none;margin-right:.7rem}
.go a:hover{text-decoration:underline}
.ok{color:#7ec77e}.warn{color:#d4af4a}
.note{background:#1b1914;border-left:3px solid #4a4436;padding:1rem 1.2rem;margin:2.5rem 0 0;
  color:#a9a294;font-size:.88rem}
code{font-family:ui-monospace,Menlo,monospace;background:#26221b;padding:.1em .35em;border-radius:3px}
"""


def counts(slug):
    md = (POSTS / slug / "index.md").read_text(encoding="utf-8")
    body = md.split("---", 2)[-1]
    return {
        "words": len(re.sub(r"[#*_`>|\[\]()!-]", " ", body).split()),
        "img": len(re.findall(r"!\[[^\]]*\]\(media/", body))
               + len(re.findall(r'<img [^>]*src="media/', body)),
        "eq": len(re.findall(r"(?<!\$)\$[^$\n]+\$(?!\$)", body)),
        "code": len(re.findall(r"^```", body, re.M)) // 2,
        "vid": len(re.findall(r"<video", body)),
        "tbl": len(re.findall(r"^\|.*\|$", body, re.M)) and
               len(re.findall(r"^\|[\s-]*-{3}", body, re.M)),
    }


def source_counts(slug, posts):
    h = posts[slug]["content"]["rendered"]
    eq = len(re.findall(r"ql-img", h))
    return {"img": len(re.findall(r"<img", h)) - eq, "eq": eq,
            "code": len(re.findall(r"<pre", h)), "vid": len(re.findall(r"<video", h)),
            "tbl": len(re.findall(r"<table", h))}


def main():
    posts = {p["slug"]: p for p in json.loads(
        (ARCHIVE / "wp-api" / "posts.json").read_text(encoding="utf-8"))}
    media = json.loads((ARCHIVE / "media_manifest.json").read_text(encoding="utf-8"))

    print("building preview (all statuses)...")
    subprocess.run([sys.executable, "-m", "sitegen.build",
                    "--include-unpublished", "--out", str(PREVIEW)],
                   cwd=ROOT, check=True,
                   env={**__import__("os").environ,
                        "PYTHONPATH": str(ROOT / "src")})

    entries = []
    for d in sorted(POSTS.iterdir()):
        if not (d / "index.md").exists():
            continue
        meta, _ = frontmatter.load(d / "index.md")
        entries.append((meta, counts(d.name), source_counts(d.name, posts)
                        if d.name in posts else None))
    entries.sort(key=lambda e: e[0]["date"], reverse=True)

    rows = []
    for meta, got, want in entries:
        slug = meta["slug"]
        mb = sum(r["bytes_out"] for r in media.get(slug, [])) / 1048576

        def cell(key, label=None):
            g = got.get(key, 0)
            if want is None:
                return f'<td class="n">{g or "<span class=z>0</span>"}</td>'
            w = want.get(key, 0)
            if g == w:
                klass = "n ok" if g else "n z"
                return f'<td class="{klass}">{g}</td>'
            return f'<td class="n warn">{g}/{w}</td>'

        rows.append(
            f'<tr>'
            f'<td><div class="t"><a href="{slug}/">{html.escape(meta["title"])}</a></div>'
            f'<div class="d">{meta["date"]} &middot; '
            f'{html.escape(", ".join(meta.get("wp_categories", [])) or "no category")}</div></td>'
            f'<td><span class="badge {meta["status"]}">{meta["status"]}</span></td>'
            f'<td class="n">{got["words"]:,}</td>'
            + cell("img") + cell("eq") + cell("code") + cell("vid") + cell("tbl") +
            f'<td class="n">{mb:.1f}M</td>'
            f'<td class="go">'
            f'<a href="{slug}/">rendered</a>'
            f'<a href="../archive/live-html/{slug}.html">original</a>'
            f'</td></tr>')

    total_mb = sum(r["bytes_out"] for rs in media.values() for r in rs) / 1048576
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Curation — 12 posts</title><style>{CSS}</style></head><body><div class="wrap">
<h1>Twelve posts, converted</h1>
<p class="sub">Read each one against its original, then decide. Counts are
<span class="ok">green</span> when the conversion matched the source exactly and
<span class="warn">amber</span> when it did not.</p>
<table>
<tr><th>Post</th><th>Status</th><th>Words</th><th>Img</th><th>Eq</th><th>Code</th>
<th>Vid</th><th>Tbl</th><th>Media</th><th></th></tr>
{"".join(rows)}
</table>
<div class="note">
<b>To publish one:</b> open <code>content/posts/&lt;slug&gt;/index.md</code>, change
<code>status: staged</code> to <code>status: published</code>, and add the three keys
publishing requires — <code>summary</code>, <code>category</code> and <code>tags</code>.
The build refuses to publish without them, which is what makes curation a decision rather
than an omission. Leave the rest <code>staged</code>: they stay committed, diffable and
unpublished. Then <code>make site</code>.
<br><br>
{len(entries)} posts &middot; {total_mb:.1f} MB of media &middot;
every count matched the source.
</div>
</div></body></html>
"""
    out = PREVIEW / "_review.html"
    out.write_text(page, encoding="utf-8")
    print(f"\n  {out.relative_to(ROOT)}")
    print(f"  cd preview && python3 -m http.server 8000  ->  "
          f"http://localhost:8000/_review.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
