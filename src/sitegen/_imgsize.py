"""Image dimensions from file headers, using only the standard library.

`make site` must be hermetic and must not depend on Pillow: Pillow is in the
`migrate` extra, it is a compiled dependency, and its behaviour moves between
releases. All this needs is width and height so the renderer can emit them on
every <img> and the page stops reflowing as figures load — and that is four
header formats and about forty lines.

Rejected: declaring dimensions in front matter (fussy, and drifts silently the
first time an image is re-exported).
"""

import struct


def size(path):
    """(width, height) or None if the format is not one of the four we emit."""
    with open(path, "rb") as fh:
        head = fh.read(32)
        if len(head) < 24:
            return None

        # PNG: IHDR is always the first chunk.
        if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
            return struct.unpack(">II", head[16:24])

        # GIF87a / GIF89a: little-endian, right after the signature.
        if head[:6] in (b"GIF87a", b"GIF89a"):
            return struct.unpack("<HH", head[6:10])

        # WebP: VP8 (lossy), VP8L (lossless), VP8X (extended) all differ.
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            fh.seek(0)
            blob = fh.read(32)
            chunk = blob[12:16]
            if chunk == b"VP8 ":
                w, h = struct.unpack("<HH", blob[26:30])
                return w & 0x3FFF, h & 0x3FFF
            if chunk == b"VP8L":
                bits = struct.unpack("<I", blob[21:25])[0]
                return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            if chunk == b"VP8X":
                w = blob[24] | blob[25] << 8 | blob[26] << 16
                h = blob[27] | blob[28] << 8 | blob[29] << 16
                return w + 1, h + 1
            return None

        # JPEG: walk the segment chain to a Start-Of-Frame marker.
        if head[:2] == b"\xff\xd8":
            fh.seek(2)
            while True:
                b = fh.read(1)
                while b and b != b"\xff":
                    b = fh.read(1)
                while b == b"\xff":
                    b = fh.read(1)
                if not b:
                    return None
                marker = b[0]
                # SOF0..SOF15, excluding the non-frame markers DHT/JPG/DAC.
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    fh.read(3)
                    h, w = struct.unpack(">HH", fh.read(4))
                    return w, h
                seg = fh.read(2)
                if len(seg) < 2:
                    return None
                fh.seek(struct.unpack(">H", seg)[0] - 2, 1)
    return None
