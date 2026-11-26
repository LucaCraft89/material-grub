#!/usr/bin/env python3
"""Convert the firmware (BGRT) logo to a tinted-silhouette PNG for the GRUB theme.
stdlib only. usage: bgrt-logo.py [in.bmp] out.png [--ink RRGGBB] [--size N]
Exit 0 and writes a fully transparent 1x1 PNG if no usable logo exists."""

import os
import struct
import sys
import zlib


def png(w, h, rows, ink):  # rows: list of alpha bytes; writes RGBA
    raw = b"".join(b"\x00" + b"".join(bytes(ink) + bytes([a]) for a in row) for row in rows)

    def ch(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
        + ch(b"IDAT", zlib.compress(raw, 9))
        + ch(b"IEND", b"")
    )


def read_bmp(path):
    d = open(path, "rb").read()
    if d[:2] != b"BM":
        raise ValueError("not a BMP")
    (off,) = struct.unpack_from("<I", d, 10)
    hs, w, h, _, bpp, comp = struct.unpack_from("<IiiHHI", d, 14)
    if bpp not in (24, 32) or comp not in (0, 3):
        raise ValueError(f"unsupported BMP {bpp}bpp comp {comp}")
    top_down = h < 0
    h = abs(h)
    bp = bpp // 8
    stride = (w * bp + 3) & ~3
    rows = []
    for y in range(h):
        r = d[off + y * stride : off + y * stride + w * bp]
        rows.append([(r[i * bp + 2], r[i * bp + 1], r[i * bp]) for i in range(w)])
    return w, h, (rows if top_down else rows[::-1])


def alpha_rows(w, h, px):
    # background = most common color among border pixels; alpha = distance from it
    border = (
        [px[0][0], px[0][w - 1], px[h - 1][0], px[h - 1][w - 1]]
        + [px[0][x] for x in range(w)]
        + [px[h - 1][x] for x in range(w)]
    )
    bg = max(set(border), key=border.count)
    far = max(abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2]) for r in px for p in r) or 1
    return [[min(255, 255 * (abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2])) // far) for p in r] for r in px]


def crop(rows, w, h, thr=8):
    ys = [y for y in range(h) if any(a > thr for a in rows[y])]
    xs = [x for x in range(w) if any(rows[y][x] > thr for y in range(h))]
    if not ys:
        return None
    x0, x1, y0, y1 = xs[0], xs[-1] + 1, ys[0], ys[-1] + 1
    return x1 - x0, y1 - y0, [r[x0:x1] for r in rows[y0:y1]]


def fit_square(w, h, rows, n):
    sc = min(n / w, n / h, 1.0) if False else n / max(w, h)
    nw, nh = max(1, round(w * sc)), max(1, round(h * sc))
    out = [[0] * n for _ in range(n)]
    ox, oy = (n - nw) // 2, (n - nh) // 2
    for y in range(nh):
        y0, y1 = int(y / sc), max(int(y / sc) + 1, min(h, int((y + 1) / sc + 0.999)))
        for x in range(nw):
            x0, x1 = int(x / sc), max(int(x / sc) + 1, min(w, int((x + 1) / sc + 0.999)))
            tot = cnt = 0
            for yy in range(y0, min(y1, h)):
                r = rows[yy]
                for xx in range(x0, min(x1, w)):
                    tot += r[xx]
                    cnt += 1
            out[oy + y][ox + x] = tot // cnt if cnt else 0
    return n, n, out


def main():
    size = 0
    if "--size" in sys.argv:
        i = sys.argv.index("--size")
        size = int(sys.argv[i + 1])
        del sys.argv[i : i + 2]
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    ink = (0x14, 0x14, 0x18)
    if "--ink" in sys.argv:
        v = sys.argv[sys.argv.index("--ink") + 1]
        ink = tuple(int(v[i : i + 2], 16) for i in (0, 2, 4))
        a = [x for x in a if x != v]
    src, out = (a[0], a[1]) if len(a) > 1 else (os.environ.get("MG_BGRT_IMAGE", "/sys/firmware/acpi/bgrt/image"), a[0])
    try:
        w, h, px = read_bmp(src)
        res = crop(alpha_rows(w, h, px), w, h)
        if res is None:
            raise ValueError("empty logo")
        w, h, rows = res
    except Exception as e:
        print("no usable BGRT logo:", e, file=sys.stderr)
        w, h, rows = 1, 1, [[0]]
    if size and w > 1:
        w, h, rows = fit_square(w, h, rows, size)
    open(out, "wb").write(png(w, h, rows, ink))
    print(f"wrote {out} {w}x{h}")


if __name__ == "__main__":
    main()
