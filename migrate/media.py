"""archive/media-original/ -> content/posts/<slug>/media/, optimised.

63.8 MB of unoptimised WordPress uploads become something a reader can
actually download: two 7 MB PNG screenshots, a 5 MB GIF, and a long tail of
3 MB screenshots that were served at full size to every visitor.

MEASURED POLICY, NOT GUESSED:

  Lossless WebP was tried and REJECTED. On the largest screenshot it produced
  4.57 MB against 1.02 MB at quality 82, and these images are photographic
  enough that 82 holds up. Both numbers are in MIGRATION.md so the decision
  stays reviewable.

  Alpha is CHECKED, not assumed. The big screenshots are RGBA with a
  fully-opaque alpha channel; flattening one that genuinely uses alpha would
  put a black box behind a transparent figure.

  Output larger than input KEEPS THE INPUT. Seven files are already WebP and
  re-encoding some of them is a loss.

  `.mov` is REMUXED, never re-encoded: the streams are already H.264 inside a
  QuickTime container, so `-c copy` changes the container and nothing else.
  Firefox will not play a .mov, and these six animations are the entire payoff
  of kochs-snowflake.

The build itself never runs any of this. Images are committed PRE-OPTIMISED,
because resizing at build time would make the committed bytes depend on a
compiled library's version and the byte-diff gate would fail on a machine with
a different Pillow.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "archive"
POSTS = ROOT / "content" / "posts"

MAX_EDGE = 1600
QUALITY = 82
GIF_QUALITY = 70
BUDGET_MB = 15.0          # verify fails above this; expectation is 9-12


def _is_opaque(im):
    if im.mode not in ("RGBA", "LA", "P"):
        return True
    if im.mode == "P" and "transparency" not in im.info:
        return True
    alpha = im.convert("RGBA").getchannel("A")
    return alpha.getextrema() == (255, 255)


def optimise_image(src, dst_dir):
    with Image.open(src) as im:
        animated = getattr(im, "n_frames", 1) > 1
        if animated:
            from PIL import ImageSequence
            dst = dst_dir / (src.stem + ".webp")
            frames_in = im.n_frames
            frames = [f.convert("RGBA") for f in ImageSequence.Iterator(im)]
            durations = [f.info.get("duration", 80)
                         for f in ImageSequence.Iterator(Image.open(src))]
            # WebP DEDUPLICATES identical consecutive frames and extends the
            # preceding frame's duration instead, which is why a 47-frame GIF
            # legitimately becomes 45. Asserting equality would fire on a
            # correct conversion; asserting that ONLY duplicates were dropped
            # still catches a real loss. The source is checked for exactly how
            # many duplicate pairs it has, so the tolerance is measured rather
            # than a fudge factor.
            dupes = sum(1 for a, b in zip(frames, frames[1:])
                        if a.tobytes() == b.tobytes())
            frames[0].save(dst, "WEBP", save_all=True, append_images=frames[1:],
                           duration=durations, loop=im.info.get("loop", 0),
                           quality=GIF_QUALITY, method=4)
            with Image.open(dst) as check:
                frames_out = getattr(check, "n_frames", 1)
            dropped = frames_in - frames_out
            assert 0 <= dropped <= dupes, (
                f"{src.name}: {frames_in} frames in, {frames_out} out — "
                f"{dropped} dropped but only {dupes} are duplicates of their "
                "predecessor, so real animation was lost")
            return dst, (im.width, im.height), frames_out

        im.load()
        opaque = _is_opaque(im)
        im = im.convert("RGB" if opaque else "RGBA")
        w, h = im.size
        if max(w, h) > MAX_EDGE:
            scale = MAX_EDGE / max(w, h)
            im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
        dst = dst_dir / (src.stem + ".webp")
        im.save(dst, "WEBP", quality=QUALITY, method=6)

    # An optimisation that makes the file bigger is not an optimisation.
    if dst.stat().st_size >= src.stat().st_size and src.suffix.lower() == ".webp":
        dst.unlink()
        dst = dst_dir / src.name
        shutil.copy2(src, dst)
    return dst, (w, h), 1


def remux_video(src, dst_dir):
    """QuickTime -> MP4 by stream copy. No re-encode, no quality change."""
    dst = dst_dir / (src.stem + ".mp4")
    if not shutil.which("ffmpeg"):
        raise SystemExit(
            "ffmpeg is not installed, and six .mov files cannot be shipped as "
            "they are — Firefox will not play a QuickTime container.\n"
            "  brew install ffmpeg")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
         "-c", "copy", "-movflags", "+faststart", str(dst)],
        check=True)
    return dst


def main():
    plan_path = ARCHIVE / "media_plan.json"
    if not plan_path.exists():
        raise SystemExit("no archive/media_plan.json — run migrate/convert.py first")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    manifest, total_in, total_out, n = {}, 0, 0, 0
    print(f"{'post':40} {'files':>5} {'in':>9} {'out':>9}  ratio")
    for slug in sorted(plan):
        media_dir = POSTS / slug / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        rows, pin, pout = [], 0, 0
        for local, src_str in sorted(plan[slug].items()):
            src = Path(src_str)
            if not src.exists():
                raise SystemExit(f"{slug}: captured file missing: {src}")
            size_in = src.stat().st_size
            if src.suffix.lower() in (".mov", ".mp4", ".m4v"):
                dst = remux_video(src, media_dir)
                dims, frames = None, 1
            elif src.suffix.lower() in (".mp3", ".ogg", ".wav"):
                dst = media_dir / src.name
                shutil.copy2(src, dst)
                dims, frames = None, 1
            else:
                dst, dims, frames = optimise_image(src, media_dir)
            size_out = dst.stat().st_size
            rows.append({
                "referenced_as": local, "source": str(src.relative_to(ARCHIVE)),
                "file": dst.name, "bytes_in": size_in, "bytes_out": size_out,
                "dimensions": list(dims) if dims else None, "frames": frames,
            })
            pin += size_in
            pout += size_out
            n += 1
        manifest[slug] = rows
        total_in += pin
        total_out += pout
        print(f"{slug[:38]:40} {len(rows):>5} {pin/1048576:>8.2f}M "
              f"{pout/1048576:>8.2f}M  {pin/max(pout,1):>5.1f}x")

    # REWRITE THE REFERENCES. convert.py emits media/<original-name> because
    # it runs before anything has been optimised; the files on disk are now
    # .webp and .mp4. Doing this here, from the manifest, keeps convert.py from
    # having to predict an encoder's output filename.
    rewritten = 0
    for slug, rows in manifest.items():
        index = POSTS / slug / "index.md"
        text = index.read_text(encoding="utf-8")
        before = text
        for row in rows:
            if row["referenced_as"] != row["file"]:
                text = text.replace(f'media/{row["referenced_as"]}',
                                    f'media/{row["file"]}')
        # A reference the manifest does not account for means a file was
        # dropped between conversion and optimisation.
        import re as _re
        for ref in _re.findall(r'media/([^\s)"\']+)', text):
            assert any(r["file"] == ref for r in rows), (
                f"{slug}: markdown references media/{ref}, which no optimised "
                "file matches")
        if text != before:
            index.write_text(text, encoding="utf-8")
            rewritten += 1
    print(f"rewrote media references in {rewritten} posts")

    (ARCHIVE / "media_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    mb = total_out / 1048576
    print(f"\n{n} files: {total_in/1048576:.1f} MB -> {mb:.1f} MB "
          f"({total_in/max(total_out,1):.1f}x smaller)")
    if mb > BUDGET_MB:
        raise SystemExit(
            f"\nFAIL: {mb:.1f} MB exceeds the {BUDGET_MB} MB budget. "
            "A target you do not check is a wish.")
    print(f"within the {BUDGET_MB} MB budget")
    return 0


if __name__ == "__main__":
    sys.exit(main())
