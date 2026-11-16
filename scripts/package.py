"""Assemble the distributable package: dist/material-grub/{scenes,res,classes.json,rules.json,bin}"""
import json, os, re, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import build_theme as B, catalog as C
ROOT = B.ROOT; PKG = ROOT / "dist/material-grub"
RES = "1280x720 1920x1080 1920x1200 2560x1080 2560x1440 3440x1440 3840x2160".split()
GENERIC = {"os", "gnu", "gnu-linux", "unknown", "win", "mx", "nix", "linux"}

def bundle(res):       # one resolution bundle (theme.txt, bitmap fonts, bar slices); independent per resolution
    w, h = map(int, res.split("x")); B.assemble(w, h, set(), pkg=PKG); return res

def prepare(asp):      # runs in a worker process: the three aspect-ratio scene sets are independent
    B.ensure_scenes(asp, set()); B.ensure_bg(asp); return asp

if __name__ == "__main__":
    from concurrent.futures import ProcessPoolExecutor
    print(f"total {len(C.ENTRIES) * 2 * len(B.ASPECTS) + len(RES)}", flush=True)   # progress denominator for the installer
    shutil.rmtree(PKG, ignore_errors=True); PKG.mkdir(parents=True)
    with ProcessPoolExecutor(max_workers=min(len(B.ASPECTS), os.cpu_count() or 1)) as ex: list(ex.map(prepare, B.ASPECTS))
    for asp in B.ASPECTS:
        shutil.copytree(ROOT / "build/scenes" / asp / "icons", PKG / "scenes" / asp / "icons"); shutil.copytree(ROOT / "build/scenes" / asp / "bg", PKG / "scenes" / asp / "bg")
    with ProcessPoolExecutor(max_workers=min(len(RES), os.cpu_count() or 1)) as ex: list(ex.map(bundle, RES))
    (PKG / "classes.json").write_text(json.dumps({k: v for k, v in C.CLASSES.items()}, indent=1))
    rules = []   # title -> canonical key, most specific first
    for k, title, _, _, _, _, al in C.D:
        pats = {title, k, *[a for a in al if a not in GENERIC]}
        for p in pats:
            toks = re.findall(r"[a-z0-9]+", p.lower())
            if toks: rules.append({"key": k, "tokens": toks})
    rules.sort(key=lambda r: -len("".join(r["tokens"])))
    (PKG / "rules.json").write_text(json.dumps(rules))
    (PKG / "titles.json").write_text(json.dumps({k: t for k, t, *_ in C.D}))
    (PKG / "fonts").mkdir(); shutil.copy(B.R.FONT, PKG / "fonts" / "GoogleSansFlex-VF.ttf")
    for n in ("OFL.txt", "TRADEMARKS.md"): shutil.copy(ROOT / "fonts" / n, PKG / "fonts" / n)
    (PKG / "fonts" / "NOTICE.txt").write_text("Google Sans Flex: SIL Open Font License 1.1 (OFL.txt). Not affiliated with or endorsed by Google; see TRADEMARKS.md. The GRUB .pf2 fonts MG-* are Modified Versions derived from it and remain under the OFL.\n")
    (PKG / "glyphs").mkdir()
    extra = {"gear": "vendor/material-symbols/settings.svg", "wrench": "vendor/material-symbols/build.svg", "kernel": "vendor/material-symbols/terminal.svg", "tag": "vendor/material-symbols/tag.svg"}
    from PIL import Image
    for k, _, _, g in C.ENTRIES:
        m = B.R.icon_mask(g, 128); im = Image.new("RGBA", (128, 128), (255, 255, 255, 255)); im.putalpha(m); im.save(PKG / "glyphs" / f"{k}.png")
    for k, g in extra.items():
        m = B.R.icon_mask(g, 128); im = Image.new("RGBA", (128, 128), (255, 255, 255, 255)); im.putalpha(m); im.save(PKG / "glyphs" / f"{k}.png")
    (PKG / "palettes.json").write_text(json.dumps({k: v for k, v in B.R.PAL.items()}))
    shutil.copytree(ROOT / "install/bin", PKG / "bin"); shutil.copy(ROOT / "scripts/bgrt-logo.py", PKG / "bin/bgrt-logo.py")
    print("package at", PKG)
