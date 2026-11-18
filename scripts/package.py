"""Assemble the distributable package: dist/material-grub/{scenes,res,classes.json,rules.json,bin}"""

import json
import os
import re
import shutil
import sys
from pathlib import Path


def opt(n, d=None):
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d


if opt("--scheme"):  # light | dark: read by palettes.py (also in the worker processes)
    if opt("--scheme") not in ("light", "dark"):
        sys.exit("--scheme must be light or dark")
    os.environ["MG_SCHEME"] = opt("--scheme")
if "--no-hints" in sys.argv:
    print(
        "note: --no-hints is a no-op at build time since 0.4 (hints are drawn at install time); the installer writes HINTS=off to /etc/material-grub.conf"
    )
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "install/bin"))
import build_theme as B
import catalog as C
import mgrub

ROOT = B.ROOT
PKG = ROOT / "dist/material-grub"
RES_ALL = mgrub.RESOLUTIONS
# --res WxH[,WxH...] builds only those resolutions and the scene sets they need (the 2160-high sets are 4x the size of the 1080-high ones)
RES = opt("--res", "").split(",") if opt("--res") else RES_ALL
SETS = list(dict.fromkeys(B.aspect_for(*map(int, r.split("x"))) for r in RES))
GENERIC = mgrub.GENERIC


def bundle(res):  # one resolution bundle (theme.txt, bitmap fonts, bar slices); independent per resolution
    w, h = map(int, res.split("x"))
    B.assemble(w, h, set(), pkg=PKG)
    return res


def prepare(asp):  # runs in a worker process: the three aspect-ratio scene sets are independent
    B.ensure_scenes(asp, set())
    B.ensure_bg(asp)
    return asp


if __name__ == "__main__":
    from concurrent.futures import ProcessPoolExecutor

    print(f"total {len(C.ENTRIES) * 2 * len(SETS) + len(RES)}", flush=True)  # progress denominator for the installer
    shutil.rmtree(PKG, ignore_errors=True)
    PKG.mkdir(parents=True)
    with ProcessPoolExecutor(max_workers=min(len(SETS), os.cpu_count() or 1)) as ex:
        list(ex.map(prepare, SETS))
    for asp in SETS:
        shutil.copytree(B.SCENES / asp / "icons", PKG / "scenes" / asp / "icons")
        shutil.copytree(B.SCENES / asp / "bg", PKG / "scenes" / asp / "bg")
    with ProcessPoolExecutor(max_workers=min(len(RES), os.cpu_count() or 1)) as ex:
        list(ex.map(bundle, RES))
    (PKG / "classes.json").write_text(json.dumps({k: v for k, v in C.CLASSES.items()}, indent=1))
    rules = []  # title -> canonical key, most specific first
    for k, title, _, _, _, _, al in C.D:
        pats = {title, k, *[a for a in al if a not in GENERIC]}
        for p in pats:
            toks = re.findall(r"[a-z0-9]+", p.lower())
            if toks:
                rules.append({"key": k, "tokens": toks})
    rules.sort(
        key=lambda r: (-len("".join(r["tokens"])), r["key"], r["tokens"])
    )  # most specific first; ties in a fixed order
    (PKG / "rules.json").write_text(json.dumps(rules))
    (PKG / "titles.json").write_text(json.dumps({k: t for k, t, *_ in C.D + C.X}))
    (PKG / "fonts").mkdir()
    shutil.copy(B.R.FONT, PKG / "fonts" / "GoogleSansFlex-VF.ttf")
    for n in ("OFL.txt", "TRADEMARKS.md"):
        shutil.copy(ROOT / "fonts" / n, PKG / "fonts" / n)
    (PKG / "fonts" / "NOTICE.txt").write_text(
        "Google Sans Flex: SIL Open Font License 1.1 (OFL.txt). Not affiliated with or endorsed by Google; see TRADEMARKS.md. The GRUB .pf2 fonts MG-* are Modified Versions derived from it and remain under the OFL.\n"
    )
    (PKG / "glyphs").mkdir()
    extra = {
        "gear": "vendor/material-symbols/settings.svg",
        "wrench": "vendor/material-symbols/build.svg",
        "kernel": "vendor/material-symbols/terminal.svg",
        "tag": "vendor/material-symbols/tag.svg",
        "folder": "vendor/material-symbols/folder.svg",
        "back": "vendor/material-symbols/arrow_back.svg",
        "play": "vendor/material-symbols/play_arrow.svg",
    }  # folder / back / play: Ventoy menu scenes
    from PIL import Image

    for k, _, _, g in C.ENTRIES:
        m = B.R.icon_mask(g, 512)
        im = Image.new("RGBA", (512, 512), (255, 255, 255, 255))
        im.putalpha(m)
        im.save(PKG / "glyphs" / f"{k}.png")
    for k, g in extra.items():
        m = B.R.icon_mask(g, 512)
        im = Image.new("RGBA", (512, 512), (255, 255, 255, 255))
        im.putalpha(m)
        im.save(PKG / "glyphs" / f"{k}.png")
    (PKG / "ventoy").mkdir()
    shutil.copy(ROOT / "vendor/ventoy/VentoyLogo.png", PKG / "ventoy" / "VentoyLogo.png")
    shutil.copy(
        ROOT / "vendor/pnlug/logo.png", PKG / "ventoy" / "pnlug.png"
    )  # the Ventoy logo drawn in the cookie on a stick
    (PKG / "scheme.txt").write_text(B.R.SCHEME + "\n")
    (PKG / "palettes.json").write_text(json.dumps({k: v for k, v in B.R.PAL.items()}))
    shutil.copytree(ROOT / "install/bin", PKG / "bin")
    shutil.copy(ROOT / "scripts/bgrt-logo.py", PKG / "bin/bgrt-logo.py")
    print("package at", PKG)
