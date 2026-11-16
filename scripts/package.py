"""Assemble the distributable package: dist/material-grub/{scenes,res,classes.json,rules.json,bin}"""
import json, re, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import build_theme as B, catalog as C
ROOT = B.ROOT; PKG = ROOT / "dist/material-grub"
RES = "1280x720 1920x1080 1920x1200 2560x1080 2560x1440 3440x1440 3840x2160".split()
GENERIC = {"os", "gnu", "gnu-linux", "unknown", "win", "mx", "nix", "linux"}

if __name__ == "__main__":
    shutil.rmtree(PKG, ignore_errors=True); PKG.mkdir(parents=True)
    for asp in B.ASPECTS:
        d = B.ensure_scenes(asp, set()); shutil.copytree(d, PKG / "scenes" / asp / "icons")
    for r in RES:
        w, h = map(int, r.split("x")); B.assemble(w, h, set(), pkg=PKG)
    (PKG / "classes.json").write_text(json.dumps({k: v for k, v in C.CLASSES.items()}, indent=1))
    rules = []   # title -> canonical key, most specific first
    for k, title, _, _, _, _, al in C.D:
        pats = {title, k, *[a for a in al if a not in GENERIC]}
        for p in pats:
            toks = re.findall(r"[a-z0-9]+", p.lower())
            if toks: rules.append({"key": k, "tokens": toks})
    rules.sort(key=lambda r: -len("".join(r["tokens"])))
    (PKG / "rules.json").write_text(json.dumps(rules))
    (PKG / "glyphs").mkdir()
    from PIL import Image
    for k, _, _, g in C.ENTRIES:
        m = B.R.icon_mask(g, 128); im = Image.new("RGBA", (128, 128), (255, 255, 255, 255)); im.putalpha(m); im.save(PKG / "glyphs" / f"{k}.png")
    (PKG / "palettes.json").write_text(json.dumps({k: v for k, v in B.R.PAL.items()}))
    shutil.copytree(ROOT / "install/bin", PKG / "bin"); shutil.copy(ROOT / "scripts/bgrt-logo.py", PKG / "bin/bgrt-logo.py")
    print("package at", PKG)
