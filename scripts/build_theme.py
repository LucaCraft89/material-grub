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
args = [a for a in sys.argv[1:] if not a.startswith("--")]
W, H = (int(args[0]), int(args[1])) if len(args) >= 2 else (1920, 1080)
OUT = ROOT / f"theme-{W}x{H}"
SF = H / 1080; WD = round(1080 * W / H)   # design width at 1080 height

INK_TRACK, INK_FILL, INK_TEXT = "#49454F", "#E6E1E5", "#CAC4D0"

def scene(entry):
    key = entry[0]; p = R.PAL[key]
    im, _ = R.panel(entry, WD + 48, ph=1080, yoff=60, dyn=False)     # pw == WD
    canvas = Image.new("RGBA", (WD, 1080), R.hx(p["surface"]) + (255,)); canvas.alpha_composite(im)
    hint = R.key_hints(p); canvas.alpha_composite(hint, ((WD - hint.width) // 2, 1080 - 120))
    out = canvas.convert("RGB")
    return out if out.size == (W, H) else out.resize((W, H), Image.LANCZOS)

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

if __name__ == "__main__":
    shutil.rmtree(OUT, ignore_errors=True); (OUT / "icons").mkdir(parents=True)
    for e in R.ENTRIES:
        img = scene(e); tmp = OUT / "icons" / f"{CLASSES[e[0]][0]}.png"; img.save(tmp, optimize=True)
        for extra in CLASSES[e[0]][1:]: shutil.copy(tmp, OUT / "icons" / f"{extra}.png")
        print("scene", e[0], img.size)
    bh = max(8, round(14 * SF)); pill_slices("bar", bh, color=INK_TRACK); pill_slices("hl", bh, color=INK_FILL)
    font("GSF-Label", 520, 105, round(26 * SF))
    px = lambda v: round(v * SF)
    subprocess.run(["python3", str(Path(__file__).parent / "bgrt-logo.py"), str(OUT / "machine-logo.png"), "--size", str(px(120))], check=True)
    cxp = px(WD / 2); barw = px(560); logo = px(120)
    lx = px(WD - 150) - logo // 2; ly = px(140) - logo // 2
    MENU = f'''+ boot_menu {{
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
  item_font = "GSF-Label Regular {round(26 * SF)}"
  selected_item_font = "GSF-Label Regular {round(26 * SF)}"
  item_color = "#00000000"
  selected_item_color = "#00000000"
  scrollbar = false
}}
'''
    theme = f'''# Material 3 Expressive GRUB theme (generated)
title-text: ""
desktop-color: "#0D1411"
terminal-font: "GSF-Label Regular {round(26 * SF)}"

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
  font = "GSF-Label Regular {round(26 * SF)}"
  text = "Booting in %d seconds"
}}
'''
    theme = theme.rstrip() + "\n\n# GRUB draws the first-declared component on top, so the menu goes last\n" + MENU
    (OUT / "theme.txt").write_text(theme); print("theme at", OUT)
