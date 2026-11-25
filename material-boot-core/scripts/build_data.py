#!/usr/bin/env python3
"""Build the data both material-grub and material-plymouth read: the catalog's palettes, classes, title rules, titles, subtitles, glyphs, the font and
the scheme marker. The same files material-grub's scripts/package.py writes into dist/material-grub today (this is that code, moved).

  python3 scripts/build_data.py --out DIR [--scheme dark|light]

Needs Pillow, and `rsvg-convert` (librsvg) or ImageMagick to rasterise the SVG glyphs. The colours come from material_boot.palette (the vendored copy
unless the pip `materialyoucolor` is installed; both give the same colours). Writes DIR/{palettes,classes,rules,titles,subtitles}.json, DIR/scheme.txt,
DIR/glyphs/*.png and DIR/fonts/*.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / "lib"))  # an installed or bundled copy keeps the library in lib/

from PIL import Image  # noqa: E402

from material_boot import catalog as C  # noqa: E402
from material_boot import palette  # noqa: E402

MASK = 512  # the size of the glyph masks in the package


def icon_mask(path, size, tmp):
    """Rasterize an SVG glyph to a size x size alpha mask (rsvg-convert preferred; ImageMagick as a fallback)."""
    out = Path(tmp) / f"icon-{os.getpid()}.png"
    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        subprocess.run([rsvg, "-a", "-w", str(size), "-h", str(size), "-o", str(out), str(ROOT / path)], check=True)
        im = Image.open(out).convert("RGBA")
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.alpha_composite(im, ((size - im.width) // 2, (size - im.height) // 2))
        return canvas.getchannel("A")
    magick = (
        [shutil.which("magick")] if shutil.which("magick") else [shutil.which("convert") or "magick"]
    )  # ImageMagick 7 / 6
    subprocess.run(
        magick
        + [
            "-background",
            "none",
            "-density",
            "600",
            str(ROOT / path),
            "-resize",
            f"{size}x{size}",
            "-gravity",
            "center",
        ]
        + ["-extent", f"{size}x{size}", "PNG32:" + str(out)],
        check=True,
    )
    return Image.open(out).convert("RGBA").getchannel("A")


def build(out, scheme="dark"):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    dark = scheme != "light"
    (out / "classes.json").write_text(json.dumps({k: v for k, v in C.CLASSES.items()}, indent=1))
    rules = []  # title -> canonical key, most specific first
    for k, title, _, _, _, _, al in C.D:
        pats = {title, k, *[a for a in al if a not in C.GENERIC]}
        for p in pats:
            toks = re.findall(r"[a-z0-9]+", p.lower())
            if toks:
                rules.append({"key": k, "tokens": toks})
    rules.sort(
        key=lambda r: (-len("".join(r["tokens"])), r["key"], r["tokens"])
    )  # most specific first; ties in a fixed order
    (out / "rules.json").write_text(json.dumps(rules))
    (out / "titles.json").write_text(json.dumps({k: t for k, t, *_ in C.D + C.X}))
    (out / "subtitles.json").write_text(json.dumps({k: sub for k, _, sub, *_ in C.D + C.X}))  # the hero subtitle
    fonts = out / "fonts"
    fonts.mkdir(exist_ok=True)
    shutil.copy(ROOT / "assets/fonts/GoogleSansFlex-VF.ttf", fonts / "GoogleSansFlex-VF.ttf")
    for n in ("OFL.txt", "TRADEMARKS.md"):
        shutil.copy(ROOT / "assets/fonts" / n, fonts / n)
    (fonts / "NOTICE.txt").write_text(
        "Google Sans Flex: SIL Open Font License 1.1 (OFL.txt). Not affiliated with or endorsed by Google; see TRADEMARKS.md. The GRUB .pf2 fonts MG-* are Modified Versions derived from it and remain under the OFL.\n"
    )
    glyphs = out / "glyphs"
    glyphs.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mb-glyphs-") as tmp:
        for k, g in [(k, g) for k, _, _, g in C.ENTRIES] + list(C.EXTRA_GLYPHS.items()):
            m = icon_mask(g, MASK, tmp)
            im = Image.new("RGBA", (MASK, MASK), (255, 255, 255, 255))
            im.putalpha(m)
            im.save(glyphs / f"{k}.png")
    (out / "scheme.txt").write_text(("dark" if dark else "light") + "\n")
    pal = {}
    for k, seed in C.SEEDS.items():
        pal[k] = {"seed": seed, **palette.scheme(seed, dark)}
    (out / "palettes.json").write_text(json.dumps(pal))
    return out


def main(argv):
    def opt(n, d=None):
        return argv[argv.index(n) + 1] if n in argv else d

    if not opt("--out") or opt("--scheme", "dark") not in ("dark", "light"):
        raise SystemExit(__doc__)
    print("data at", build(opt("--out"), opt("--scheme", "dark")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
