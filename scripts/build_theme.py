"""Build the GRUB theme. usage: build_theme.py [WIDTH HEIGHT] [--peek-test]"""
import subprocess, sys, shutil
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).parent))
import render_scene as R
from catalog import CLASSES
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = R.ROOT
ASPECTS = {"16x9": 1920, "16x10": 1728, "21x9": 2560}   # design width at 1080 high
def aspect_for(w, h): return min(ASPECTS, key=lambda k: abs(ASPECTS[k] / 1080 - w / h))
opt = lambda n, d=None: sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d
WD = 1920  # set per aspect in scene()

INK_TRACK, INK_FILL, INK_TEXT = "#49454F", "#E6E1E5", "#CAC4D0"

def scene(entry, hero=True):
    key = entry[0]; p = R.PAL[key]
    im, _ = R.panel(entry, WD + 48, ph=1080, yoff=60, dyn=False, hero=hero)     # pw == WD
    canvas = Image.new("RGBA", (WD, 1080), R.hx(p["surface"]) + (255,)); canvas.alpha_composite(im)
    hint = R.key_hints(p); canvas.alpha_composite(hint, ((WD - hint.width) // 2, 1080 - 120))
    return canvas.convert("RGB")

OUT = None
def pill_slices(prefix, h, w=64, color="#FFFFFF"):
    S = 4; r = h // 2
    im = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w * S - 1, h * S - 1], radius=r * S, fill=color)
    im = im.resize((w, h), Image.LANCZOS)
    cs = r - 1  # corner slice size, leaves a 2px centre
    xs = [(0, cs), (cs, w - cs), (w - cs, w)]; ys = [(0, cs), (cs, h - cs), (h - cs, h)]
    names = [["nw", "n", "ne"], ["w", "c", "e"], ["sw", "s", "se"]]
    for j, (y0, y1) in enumerate(ys):
        for i, (x0, x1) in enumerate(xs):
            im.crop((x0, y0, x1, y1)).save(OUT / f"{prefix}_{names[j][i]}.png")

def font(name, wght, wdth, size):
    tmp = ROOT / "build/_inst.ttf"
    f = TTFont(R.FONT)
    f = instantiateVariableFont(f, {"wght": wght, "wdth": wdth, "opsz": min(144, size), "GRAD": 0, "ROND": 0, "slnt": 0})
    f.save(tmp)
    subprocess.run(["grub2-mkfont", "-s", str(size), "-n", name, "-r", "0x20-0x7e,0xa0-0x17f,0x2013-0x2026",
                    "-o", str(OUT / f"{name}.pf2"), str(tmp)], check=True)

def ensure_bg(aspect):
    global WD
    WD = ASPECTS[aspect]; d = ROOT / "build/scenes" / aspect / "bg"; d.mkdir(parents=True, exist_ok=True)
    for e in R.ENTRIES:
        f = d / f"{e[0]}.png"
        if not f.exists() or "--rescene" in sys.argv: scene(e, hero=False).save(f, optimize=True); print("bg", aspect, e[0])
    return d

def ensure_scenes(aspect, only):
    global WD
    WD = ASPECTS[aspect]; d = ROOT / "build/scenes" / aspect / "icons"; d.mkdir(parents=True, exist_ok=True)
    for e in R.ENTRIES:
        if only and e[0] not in only: continue
        f = d / f"{CLASSES[e[0]][0]}.png"
        if not f.exists() or "--rescene" in sys.argv:
            scene(e).save(f, optimize=True); print("scene", aspect, e[0])
    return d

def assemble(W, H, only, pkg=None):
    aspect = aspect_for(W, H); src = ensure_scenes(aspect, only)
    OUT = (pkg / "res" / f"{W}x{H}") if pkg else ROOT / f"theme-{W}x{H}"
    shutil.rmtree(OUT, ignore_errors=True); OUT.mkdir(parents=True)
    SF = H / 1080; WDs = ASPECTS[aspect]
    if not pkg:
        (OUT / "icons").mkdir()
        for e in R.ENTRIES:
            if only and e[0] not in only: continue
            f = src / f"{CLASSES[e[0]][0]}.png"
            for c in CLASSES[e[0]]: shutil.copy(f, OUT / "icons" / f"{c}.png")
    globals()["OUT"] = OUT
    bh = max(8, round(14 * SF)); pill_slices("bar", bh, color=INK_TRACK); pill_slices("hl", bh, color=INK_FILL)
    fs = round(26 * SF); font("GSF-Label", 520, 105, fs); rs = max(12, round(20 * SF)); font("GSF-Raw", 450, 100, rs)
    px = lambda v: round(v * SF)
    if pkg: (OUT / "logo_size").write_text(str(px(120))); (OUT / "aspect").write_text(aspect)
    else: subprocess.run(["python3", str(Path(__file__).parent / "bgrt-logo.py"), str(OUT / "machine-logo.png"), "--size", str(px(120))], check=True)
    cxp = px(WDs / 2); barw = px(560); logo = px(120)
    lx = px(WDs - 150) - logo // 2; ly = px(140) - logo // 2
    FN = f"GSF-Label Regular {fs}"; RN = f"GSF-Raw Regular {rs}"
    (OUT / "theme.txt").write_text(f'''# Material 3 Expressive GRUB theme (generated for {W}x{H}, {aspect} scenes)
title-text: ""
desktop-color: "#0D1411"
terminal-font: "{FN}"

# raw entry name (debug/clarity): a 1-item list that only ever shows the selected entry
+ boot_menu {{
  left = {px(96)}
  top = {H - px(58)}
  width = {W - px(192)}
  height = {px(34)}
  item_height = {px(34)}
  item_spacing = 0
  item_padding = 0
  item_icon_space = 0
  icon_width = 1
  icon_height = 1
  item_font = "{RN}"
  selected_item_font = "{RN}"
  item_color = "#6E7681"
  selected_item_color = "#6E7681"
  scrollbar = false
}}

+ image {{
  left = {lx}
  top = {ly}
  width = {logo}
  height = {logo}
  file = "machine-logo.png"
}}

+ progress_bar {{
  id = "__timeout__"
  left = {cxp - barw // 2}
  top = {px(755)}
  width = {barw}
  height = {bh}
  bar_style = "bar_*.png"
  highlight_style = "hl_*.png"
}}

+ label {{
  id = "__timeout__"
  left = {cxp - barw // 2}
  top = {px(790)}
  width = {barw}
  height = {px(34)}
  align = "center"
  color = "{INK_TEXT}"
  font = "{FN}"
  text = "Booting in %d seconds"
}}

# GRUB draws the first-declared component on top, so the menu goes last
+ boot_menu {{
  left = 0
  top = 0
  width = {W}
  height = {H}
  item_height = {H}
  item_spacing = 0
  item_padding = 0
  item_icon_space = 0
  icon_width = {W}
  icon_height = {H}
  item_font = "{FN}"
  selected_item_font = "{FN}"
  item_color = "#00000000"
  selected_item_color = "#00000000"
  scrollbar = false
}}
''')
    print("theme at", OUT)

if __name__ == "__main__":
    only = set(opt("--only", "").split(",")) - {""}
    for res in (opt("--res", "1920x1080")).split(","):
        w, h = map(int, res.split("x")); assemble(w, h, only)
