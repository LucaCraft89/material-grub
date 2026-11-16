"""Generate dark M3 Expressive palettes per boot entry; write JSON + swatch sheet."""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from materialyoucolor.hct import Hct
from materialyoucolor.scheme.scheme_expressive import SchemeExpressive
from materialyoucolor.scheme.scheme_tonal_spot import SchemeTonalSpot
from materialyoucolor.scheme.scheme_vibrant import SchemeVibrant
VARIANTS = {'expressive': SchemeExpressive, 'tonalspot': SchemeTonalSpot, 'vibrant': SchemeVibrant}
from materialyoucolor.dynamiccolor.material_dynamic_colors import MaterialDynamicColors as M

ROOT = Path(__file__).resolve().parent.parent
SEEDS = {
    "base": "#0B3D2E", "fedora": "#294172", "arch": "#00A6B2", "ubuntu": "#E95420",
    "debian": "#A80030", "tux": "#FFB300", "windows": "#0078D4",
    "firmware": "#7E57C2", "reboot": "#2E9E5B", "shutdown": "#C62828",
}
ROLES = ["primary", "onPrimary", "primaryContainer", "onPrimaryContainer", "secondary",
         "secondaryContainer", "tertiary", "tertiaryContainer", "surface",
         "surfaceContainer", "surfaceContainerHigh", "onSurface", "onSurfaceVariant", "outline"]

import sys; sys.path.insert(0, str(Path(__file__).parent))
def argb(h): return 0xFF000000 | int(h.lstrip("#"), 16)
def hexs(a): return "#%06X" % (a & 0xFFFFFF)

import os
SCHEME = os.environ.get("MG_SCHEME", "dark")      # "dark" (default) or "light"; set by package.py --scheme / install.sh --scheme
def scheme(seed, variant='expressive', dark=None):
    s = VARIANTS[variant](Hct.from_int(argb(seed)), (SCHEME != "light") if dark is None else dark, 0.0)
    return {r: hexs(getattr(M, r).get_hct(s).to_int()) for r in ROLES}

if __name__ == "__main__":
    seeds = json.loads((ROOT / "seeds.json").read_text()) if (ROOT / "seeds.json").exists() else SEEDS
    VAR = sys.argv[1] if len(sys.argv) > 1 else "expressive"
    pal = {k: {"seed": v, **scheme(v, VAR)} for k, v in seeds.items()}
    (ROOT / ("build/palettes-%s.json" % VAR)).write_text(json.dumps(pal, indent=1))
    f = ImageFont.truetype(__import__("render_scene").FONT, 18)
    cw, rh = 70, 64
    W, H = 150 + cw * len(ROLES), 40 + rh * len(pal)
    im = Image.new("RGB", (W, H), "#101412"); d = ImageDraw.Draw(im)
    for i, r in enumerate(ROLES):
        d.text((150 + i * cw + 4, 8), r[:9], fill="#aaa", font=ImageFont.truetype(f.path, 10))
    for j, (k, p) in enumerate(pal.items()):
        y = 40 + j * rh
        d.text((10, y + 20), f"{k}\n{p['seed']}", fill="#eee", font=f)
        for i, r in enumerate(ROLES):
            d.rectangle([150 + i * cw, y, 150 + (i + 1) * cw - 2, y + rh - 4], fill=p[r])
    im.save(ROOT / ("build/swatches-%s.png" % VAR)); print("done", len(pal))
