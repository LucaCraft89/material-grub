"""Render M3-Expressive boot panels + a stacked mockup. usage: render_scene.py WIDTH [entry]"""
import json, math, os, shutil, socket, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageChops, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
def _find_font():
    """Google Sans Flex variable font: $GSF_FONT, else common locations, else fontconfig."""
    import glob, os
    if os.environ.get("GSF_FONT"): return os.environ["GSF_FONT"]
    for pat in (str(ROOT / "fonts/GoogleSansFlex*.ttf"), "~/.local/share/fonts/**/GoogleSansFlex*.ttf", "~/.fonts/**/GoogleSansFlex*.ttf", "/usr/share/fonts/**/GoogleSansFlex*.ttf"):
        hits = sorted(glob.glob(os.path.expanduser(pat), recursive=True))
        if hits: return hits[0]
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", "Google Sans Flex"], capture_output=True, text=True).stdout
        if "GoogleSansFlex" in out: return out
    except Exception: pass
    raise SystemExit("Google Sans Flex not found (expected in fonts/). Set GSF_FONT=/path/to/GoogleSansFlex-VariableFont_*.ttf")
FONT = _find_font()
H = 1080
SS = 3  # supersample for shapes
SC = 1  # scene scale: every design coordinate below is in 1080-high pixels and goes through u() (build_theme sets SC=2 for the 2160-high sets)
def u(v): return round(v * SC)

from catalog import ENTRIES, SEEDS, CLASSES
from palettes import scheme
PAL = {k: {"seed": v, **scheme(v)} for k, v in SEEDS.items()}

IM = [shutil.which("magick")] if shutil.which("magick") else [shutil.which("convert") or "magick"]   # ImageMagick 7 / 6

def font(size, wght=400, wdth=100, rond=0, opsz=None):
    f = ImageFont.truetype(FONT, size)
    want = {"optical": opsz or size * 0.75, "width": wdth, "weight": wght, "roundness": rond, "grade": 0, "slant": 0}
    vals = []
    for ax in f.get_variation_axes():       # look axes up by name: robust across font versions (GRAD was removed in v5)
        n = ax["name"].decode() if isinstance(ax["name"], bytes) else ax["name"]
        v = next((want[k] for k in want if k in n.lower()), ax["default"])
        vals.append(min(max(v, ax["minimum"]), ax["maximum"]))
    f.set_variation_by_axes(vals); return f

def hx(c): return tuple(int(c[i:i+2], 16) for i in (1, 3, 5))

_icon_cache = {}
def icon_mask(path, size):
    """Rasterize an SVG glyph to a size x size alpha mask (rsvg-convert preferred; ImageMagick as a fallback)."""
    k = (path, size)
    if k not in _icon_cache:
        out = ROOT / f"build/_icon_{os.getpid()}.png"; out.parent.mkdir(exist_ok=True)
        rsvg = shutil.which("rsvg-convert")
        if rsvg:
            subprocess.run([rsvg, "-a", "-w", str(size), "-h", str(size), "-o", str(out), str(ROOT / path)], check=True)
            im = Image.open(out).convert("RGBA"); canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            canvas.alpha_composite(im, ((size - im.width) // 2, (size - im.height) // 2)); mask = canvas.getchannel("A")
        else:
            subprocess.run(IM + ["-background", "none", "-density", "600", str(ROOT / path), "-resize", f"{size}x{size}",
                                 "-gravity", "center", "-extent", f"{size}x{size}", "PNG32:" + str(out)], check=True)
            mask = Image.open(out).convert("RGBA").getchannel("A")
        _icon_cache[k] = mask
    return _icon_cache[k]

def tinted(mask, color):
    im = Image.new("RGBA", mask.size, hx(color) + (255,)); im.putalpha(mask); return im

# ---- shape masks (L mode), drawn supersampled ----
def poly_mask(size, fn, n=720):
    S = size * SS; im = Image.new("L", (S, S), 0); c = S / 2
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        r = fn(t) * c
        pts.append((c + r * math.cos(t), c + r * math.sin(t)))
    ImageDraw.Draw(im).polygon(pts, fill=255)
    return im.resize((size, size), Image.LANCZOS)

def flower(size): return poly_mask(size, lambda t: 0.80 + 0.17 * math.cos(8 * t))
def cookie(size): return poly_mask(size, lambda t: 0.90 + 0.06 * math.cos(9 * t))
def sunny(size):  return poly_mask(size, lambda t: 0.82 + 0.15 * (abs(math.cos(6 * t)) ** 0.6))
def clover(size): return poly_mask(size, lambda t: 0.62 + 0.36 * abs(math.cos(2 * t)) ** 0.7)

def pill(w, h):
    S = SS; im = Image.new("L", (w * S, h * S), 0)
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w * S - 1, h * S - 1], radius=h * S // 2, fill=255)
    return im.resize((w, h), Image.LANCZOS)

def rrect(w, h, r):
    im = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], radius=r * SS, fill=255)
    return im.resize((w, h), Image.LANCZOS)

def paste_c(dst, src, cx, cy):
    dst.alpha_composite(src, (int(cx - src.width / 2), int(cy - src.height / 2)))

def fill(mask, color, alpha=255):
    im = Image.new("RGBA", mask.size, hx(color) + (255,))
    im.putalpha(mask.point(lambda v: v * alpha // 255)); return im

def text_c(d, xy, s, f, color, anchor="mm"):
    d.text(xy, s, font=f, fill=hx(color), anchor=anchor)

def chip(label, icon, p, h=56, pad=22):
    f = font(26, 560, 105)
    tw = int(f.getlength(label)); iw = h - 24
    w = pad * 2 + (iw + 12 if icon else 0) + tw
    im = fill(pill(w, h), p["surfaceContainerHigh"])
    d = ImageDraw.Draw(im); x = pad
    if icon:
        im.alpha_composite(tinted(icon_mask(icon, iw), p["primary"]), (x, 12)); x += iw + 12
    d.text((x, h // 2 + 1), label, font=f, fill=hx(p["onSurface"]), anchor="lm")
    return im

def machine_logo(p, size):
    g = Image.open(ROOT / "build/bgrt.png").convert("L").resize((size, size), Image.LANCZOS)
    return tinted(g, p["onPrimaryContainer"])

def panel(entry, W, ph=888, yoff=0, dyn=True, hero=True):
    key, title, sub, icon = entry; p = PAL[key]
    pw = W - u(48); R64 = u(64)
    im = fill(rrect(pw, ph, R64), p["surface"]); d = ImageDraw.Draw(im)
    cx = pw // 2
    # decorative expressive shapes, clipped to panel
    deco = Image.new("RGBA", im.size, (0, 0, 0, 0))
    paste_c(deco, fill(cookie(u(620)), p["surfaceContainerHigh"]), cx - int(pw * .36), ph - u(120))
    paste_c(deco, fill(sunny(u(460)), p["surfaceContainer"]), cx + int(pw * .34), ph - u(60))
    paste_c(deco, fill(clover(u(300)), p["surfaceContainer"]), cx - int(pw * .29), u(150))
    clip = Image.new("L", im.size, 0); clip.paste(rrect(pw, ph, R64))
    deco.putalpha(ImageChops.multiply(deco.getchannel("A"), clip))
    im.alpha_composite(deco)
    d = ImageDraw.Draw(im)
    if hero:
        # hero pill
        pw_, ph_ = u(560), u(280)
        paste_c(im, fill(pill(pw_ + u(40), ph_ + u(40)), p["surfaceContainerHigh"]), cx, u(300) + yoff)
        paste_c(im, fill(pill(pw_, ph_), p["primaryContainer"]), cx, u(300) + yoff)
        paste_c(im, tinted(icon_mask(icon, u(230)), p["onPrimaryContainer"]), cx, u(300) + yoff)
        # name + subtitle
        tsz = u(150)
        while tsz > u(60) and font(tsz, 800, 135, rond=60, opsz=144).getlength(title) > pw * 0.62: tsz -= u(6)
        text_c(d, (cx, u(530) + yoff), title, font(tsz, 800, 135, rond=60, opsz=144), p["primary"])
        text_c(d, (cx, u(644) + yoff), sub, font(u(40), 420, 105), p["onSurfaceVariant"])
    if dyn:
        # countdown: wavy track (static preview, 62% filled)
        bw, by = 560, 695; x0 = cx - bw // 2
        pts = lambda a, b: [(x, by + 7 * math.sin((x - x0) / 14)) for x in range(a, b)]
        d.line(pts(x0 + int(bw * .62) + 14, x0 + bw), fill=hx(p["outline"]), width=6)
        d.line(pts(x0, x0 + int(bw * .62)), fill=hx(p["primary"]), width=8, joint="curve")
        d.ellipse([x0 + int(bw * .62) + 3, by - 6, x0 + int(bw * .62) + 9, by + 6], fill=hx(p["primary"]))
        text_c(d, (cx, 735), "Booting in 5s", font(24, 480, 100), p["onSurfaceVariant"])
    # machine logo in cookie (top-right)
    paste_c(im, fill(cookie(u(230)), p["primaryContainer"]), pw - u(150), u(140))
    c = chip(title, icon, p, h=52)    # edge label chip (mockup only)
    return im, c

def key_hints(p):
    items = ["Arrows  select", "Enter  boot", "E  edit", "C  console"]
    f = font(u(24), 520, 105); parts = []; hh = u(46)
    for s in items:
        w = int(f.getlength(s)) + u(44)
        im = fill(pill(w, hh), p["surfaceContainerHigh"]); ImageDraw.Draw(im).text((w // 2, hh // 2 + u(1)), s, font=f, fill=hx(p["onSurfaceVariant"]), anchor="mm")
        parts.append(im)
    gap = u(14); tot = sum(i.width for i in parts) + gap * (len(parts) - 1)
    out = Image.new("RGBA", (tot, hh), (0, 0, 0, 0)); x = 0
    for i in parts: out.alpha_composite(i, (x, 0)); x += i.width + gap
    return out

def mockup(W, idx):
    prev, cur, nxt = (ENTRIES[(idx + k) % len(ENTRIES)] for k in (-1, 0, 1))
    bg = hx(PAL["base"]["surface"]); canvas = Image.new("RGBA", (W, H), bg + (255,))
    ph, gap, top = 888, 12, 96
    for e, y in ((prev, top - gap - ph), (cur, top), (nxt, top + ph + gap)):
        im, c = panel(e, W, ph)
        im.alpha_composite(c, ((im.width - c.width) // 2, 16))               # top label chip
        im.alpha_composite(c, ((im.width - c.width) // 2, ph - c.height - 16))  # bottom label chip
        canvas.alpha_composite(im, (24, y)) if y + ph > 0 and y < H else None
    lg = Image.open(ROOT / "build/machine-logo.png").convert("RGBA")  # live overlay, one neutral ink
    sc = 120 / max(lg.size); lg = lg.resize((max(1, int(lg.width * sc)), max(1, int(lg.height * sc))), Image.LANCZOS)
    paste_c(canvas, lg, W - 24 - 150, top + 140)
    hint = key_hints(PAL[cur[0]]); canvas.alpha_composite(hint, ((W - hint.width) // 2, top + ph - 140))
    return canvas.convert("RGB")

if __name__ == "__main__":
    W = int(sys.argv[1]) if len(sys.argv) > 1 else 1920
    for i in ([int(sys.argv[2])] if len(sys.argv) > 2 else [0]):
        mockup(W, i).save(ROOT / f"build/mockup-{W}-{ENTRIES[i][0]}.png")
        print("saved", W, ENTRIES[i][0])
