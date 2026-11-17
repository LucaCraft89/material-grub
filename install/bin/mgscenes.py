"""Scene renderer shared by material-grub-scenes (config time), scripts/ (distro gallery) and, later, other targets. Pillow + stdlib only.
Importable without side effects: build a Renderer, then call its draw_* / render_entry methods.
Every coordinate is a 1080-high design value passed through u(), which scales with the scene height."""
import json, math, os, subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

WIN, SYS = {"windows10", "windows11"}, {"firmware", "reboot", "shutdown"}
STYLES = ("rail", "clean", "list")
hexc = lambda c: tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))

def poly_mask(size, fn, ss=3, n=720):
    S = size * ss; im = Image.new("L", (S, S), 0); c = S / 2; pts = []
    for i in range(n):
        t = 2 * math.pi * i / n; r = fn(t) * c; pts.append((c + r * math.cos(t), c + r * math.sin(t)))
    ImageDraw.Draw(im).polygon(pts, fill=255)
    return im.resize((size, size), Image.LANCZOS)
SHAPES = {   # same outlines as scripts/render_scene.py (the build-time panels)
    "flower": lambda t: 0.80 + 0.17 * math.cos(8 * t), "cookie": lambda t: 0.90 + 0.06 * math.cos(9 * t),
    "sunny": lambda t: 0.82 + 0.15 * (abs(math.cos(6 * t)) ** 0.6), "clover": lambda t: 0.62 + 0.36 * abs(math.cos(2 * t)) ** 0.7}

def groups_of(keys):
    return [g for g in ([k for k in keys if k not in WIN | SYS], [k for k in keys if k in WIN], [k for k in ("firmware", "reboot", "shutdown") if k in keys]) if g]

class Renderer:
    def __init__(self, pkg, height=1080, light=None, font_path=None):
        self.pkg = Path(pkg); self.H = height; self.S = height / 1080
        self.SS = 3 if self.S <= 1 else 2            # supersampling of rail/pill shapes (cheaper on the 2160-high sets)
        self.pal = json.loads((self.pkg / "palettes.json").read_text()); self.titles = json.loads((self.pkg / "titles.json").read_text())
        sch = self.pkg / "scheme.txt"; self.light = light if light is not None else (sch.exists() and sch.read_text().strip() == "light")
        self.font_path = str(font_path or self.pkg / "fonts/GoogleSansFlex-VF.ttf")
        self._g, self._nd, self._fb = {}, {}, {}
        u = self.u
        self.SLOT, self.GAP, self.DIV, self.PADV, self.RW, self.LM = u(72), u(10), u(30), u(22), u(100), u(52)   # rail metrics

    def u(self, v): return round(v * self.S)

    # ---- fonts / glyphs ----
    def font(self, size, wght=500, wdth=100, rond=0):
        f = ImageFont.truetype(self.font_path, size)
        want = {"optical": size * .75, "width": wdth, "weight": wght, "roundness": rond, "grade": 0, "slant": 0}
        vals = []
        for ax in f.get_variation_axes():   # by name: works with any version of the font (GRAD removed in v5)
            n = ax["name"].decode() if isinstance(ax["name"], bytes) else ax["name"]
            v = next((want[k] for k in want if k in n.lower()), ax["default"]); vals.append(min(max(v, ax["minimum"]), ax["maximum"]))
        f.set_variation_by_axes(vals); return f
    def _render(self, f, c):
        im = Image.new("L", (96, 96)); ImageDraw.Draw(im).text((8, 8), c, font=f, fill=255); return im.tobytes()
    def has_glyphs(self, f, text):    # a character the font lacks renders as its .notdef glyph; compare with a codepoint no font maps
        nd = self._nd.setdefault(id(f), self._render(f, "\U0010FFFF"))
        return all(c.isspace() or self._render(f, c) != nd for c in text)
    def fallback_font(self, text, size):
        """Google Sans Flex is Latin only: for pills with other scripts use any installed font that has the characters (fontconfig, else common paths)."""
        want = sorted({c for c in text if ord(c) > 0x24f})[:6]; key = tuple(want)
        if key not in self._fb:
            cands = []
            try: cands.append(subprocess.run(["fc-match", "-f", "%{file}", "sans:charset=" + " ".join("%x" % ord(c) for c in want)], capture_output=True, text=True, timeout=5).stdout.strip())
            except Exception: pass
            cands += ["/usr/share/fonts/noto/NotoSans-Regular.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf"]
            self._fb[key] = next((c for c in cands if c and os.path.exists(c)), None)
        return ImageFont.truetype(self._fb[key], size) if self._fb[key] else None
    def text_font(self, text, size, wght=500, wdth=100, rond=0):
        f = self.font(size, wght, wdth, rond)
        if all(ord(c) < 0x250 for c in text) or self.has_glyphs(f, text): return f
        return self.fallback_font(text, size) or f
    def glyph(self, name, size, color):
        a = self._g.setdefault(name, Image.open(self.pkg / "glyphs" / f"{name}.png").convert("RGBA").getchannel("A"))
        im = Image.new("RGBA", (size, size), color); im.putalpha(a.resize((size, size), Image.LANCZOS)); return im

    # ---- primitives ----
    def rrect(self, w, h, r, fill):
        SS = self.SS; im = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0)); ImageDraw.Draw(im).rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], radius=r * SS, fill=fill)
        return im.resize((w, h), Image.LANCZOS)
    @staticmethod
    def paste_c(dst, src, cx, cy): dst.alpha_composite(src, (round(cx - src.width / 2), round(cy - src.height / 2)))
    def shape(self, name, size, color):
        """An M3 shape (cookie, flower, sunny, clover) filled with `color`; 3x supersampled like the build-time panels."""
        im = Image.new("RGBA", (size, size), hexc(color) + (255,)); im.putalpha(poly_mask(size, SHAPES[name])); return im

    def pill(self, text, p, style="plain", icon=None, h=None):
        u = self.u; h = h or u(58)
        f = self.text_font(text, u(28), 560, 104); tw = int(f.getlength(text)); ic = u(30) if icon else 0
        w = u(28) * 2 + tw + (ic + u(10) if icon else 0)
        bg, fg = ((hexc(p["primaryContainer"]), hexc(p["onPrimaryContainer"])) if style == "accent" else (hexc(p["surfaceContainerHigh"]), hexc(p["onSurface"])))
        im = self.rrect(w, h, h // 2, bg + (255,)); d = ImageDraw.Draw(im); x = u(28)
        if icon: im.alpha_composite(self.glyph(icon, ic, fg + (255,)), (x, (h - ic) // 2)); x += ic + u(10)
        d.text((x, h // 2 + u(1)), text, font=f, fill=fg + (255,), anchor="lm"); return im
    def pill_row(self, items, p, W, y, canvas):
        pills = [self.pill(*i[:1], p, *i[1:]) for i in items]; g = self.u(14)
        while pills and sum(x.width for x in pills) + g * (len(pills) - 1) > W * 0.78: pills.pop()
        tot = sum(x.width for x in pills) + g * (len(pills) - 1); x = (W - tot) // 2
        for pl in pills: canvas.alpha_composite(pl, (x, y)); x += pl.width + g

    # ---- text model ----
    @staticmethod
    def info_pills(e):
        kind = e["kind"]; os_ = " ".join(x for x in (e.get("os"), e.get("osver")) if x)
        if kind == "kernel":
            out = [(e["kver"], "accent", "kernel")] if e.get("kver") else []
            if os_: out.append((os_, "plain", None))
            if e.get("edition"): out.append((e["edition"], "plain", None))
            if e.get("default"): out.append(("Default", "plain", "tag"))
            return out or [(e["title"], "plain", None)]
        if kind == "rescue":
            out = [("Rescue mode", "accent", "wrench")]
            if e.get("kver") and not e["kver"].startswith("0-rescue"): out.append((e["kver"], "plain", "kernel"))
            if os_: out.append((os_, "plain", None))
            return out
        if kind == "advanced":
            out = [("Advanced options", "accent", "gear")]
            if e.get("count"): out.append((f"{e['count']} more entries", "plain", None))
            return out
        return []
    def title_for(self, e): return {"advanced": "Advanced", "rescue": "Rescue"}.get(e["kind"]) or self.titles.get(e["key"], e["key"])

    # ---- cookie (top-right) and key hints: drawn at config time, so they are runtime options ----
    def draw_cookie(self, canvas, p):
        u = self.u; W = canvas.width; c = self.shape("cookie", u(230), p["primaryContainer"])
        canvas.alpha_composite(c, (int(W - u(150) - c.width / 2), int(u(140) - c.height / 2)))
    def key_hints(self, p):
        u = self.u; f = self.font(u(24), 520, 105); hh = u(46); parts = []
        for s in ["Arrows  select", "Enter  boot", "E  edit", "C  console"]:
            w = int(f.getlength(s)) + u(44); m = Image.new("L", (w * 3, hh * 3), 0)
            ImageDraw.Draw(m).rounded_rectangle([0, 0, w * 3 - 1, hh * 3 - 1], radius=hh * 3 // 2, fill=255)
            im = Image.new("RGBA", (w, hh), hexc(p["surfaceContainerHigh"]) + (255,)); im.putalpha(m.resize((w, hh), Image.LANCZOS))
            ImageDraw.Draw(im).text((w // 2, hh // 2 + u(1)), s, font=f, fill=hexc(p["onSurfaceVariant"]), anchor="mm"); parts.append(im)
        gap = u(14); tot = sum(i.width for i in parts) + gap * (len(parts) - 1); out = Image.new("RGBA", (tot, hh), (0, 0, 0, 0)); x = 0
        for i in parts: out.alpha_composite(i, (x, 0)); x += i.width + gap
        return out
    def draw_hints(self, canvas, p):
        hint = self.key_hints(p); canvas.alpha_composite(hint, ((canvas.width - hint.width) // 2, canvas.height - self.u(120)))

    # ---- rail ----
    def draw_rail(self, canvas, p, groups, sel):
        u, SS, SLOT, GAP, DIV, PADV, RW, LM = self.u, self.SS, self.SLOT, self.GAP, self.DIV, self.PADV, self.RW, self.LM
        n = sum(map(len, groups)); Hr = n * SLOT + (n - len(groups)) * GAP + (len(groups) - 1) * DIV + 2 * PADV
        W, H = canvas.size; top = (H - Hr) // 2
        layer = Image.new("RGBA", (RW * SS, Hr * SS), (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
        d.rounded_rectangle([0, 0, RW * SS - 1, Hr * SS - 1], radius=RW * SS // 2, fill=hexc(p["surfaceContainerHigh"]) + (255,))
        y = PADV; slots = []
        for gi, g in enumerate(groups):
            if gi:
                ly = y + DIV // 2 - GAP // 2
                d.rounded_rectangle([(RW // 2 - u(14)) * SS, ly * SS, (RW // 2 + u(14)) * SS, (ly + u(2)) * SS], radius=SS, fill=hexc(p["outline"]) + (150,)); y += DIV - GAP
            for k in g: slots.append((k, y)); y += SLOT + GAP
        for k, sy in slots:
            if k == sel: d.rounded_rectangle([(RW - SLOT) // 2 * SS, sy * SS, ((RW + SLOT) // 2) * SS - 1, (sy + SLOT) * SS - 1], radius=u(26) * SS, fill=hexc(p["primaryContainer"]) + (255,))
        layer = layer.resize((RW, Hr), Image.LANCZOS)
        for k, sy in slots:
            layer.alpha_composite(self.glyph(k, u(40), hexc(p["onPrimaryContainer"]) + (255,) if k == sel else (hexc(p["onSurfaceVariant"]) + (255,) if self.light else (244, 244, 247, 235))), ((RW - u(40)) // 2, sy + (SLOT - u(40)) // 2))
        canvas.alpha_composite(layer, (LM, top))

    # ---- scenes ----
    def decorate(self, canvas, p, opts):
        """Runtime overlays that every style shares: top-right cookie (COOKIE) and key-hint pills (HINTS)."""
        if opts.get("cookie", True): self.draw_cookie(canvas, p)
        if opts.get("hints", True): self.draw_hints(canvas, p)
    def hero(self, canvas, e, p):
        u = self.u; W = canvas.width; cx = W // 2; paste_c = self.paste_c
        paste_c(canvas, self.rrect(u(600), u(320), u(160), hexc(p["surfaceContainerHigh"]) + (255,)), cx, u(360))
        paste_c(canvas, self.rrect(u(560), u(280), u(140), hexc(p["primaryContainer"]) + (255,)), cx, u(360))
        ink = hexc(p["onPrimaryContainer"]) + (255,); acc = {"advanced": "gear", "rescue": "wrench"}.get(e["kind"])
        if acc: paste_c(canvas, self.glyph(e["key"], u(190), ink), cx - u(92), u(360)); paste_c(canvas, self.glyph(acc, u(120), ink), cx + u(140), u(360))
        else: paste_c(canvas, self.glyph(e["key"], u(230), ink), cx, u(360))
        d = ImageDraw.Draw(canvas); title = self.title_for(e); tsz = u(150)
        while tsz > u(60) and self.font(tsz, 800, 135, 60).getlength(title) > W * .62: tsz -= u(6)
        d.text((cx, u(590)), title, font=self.font(tsz, 800, 135, 60), fill=hexc(p["primary"]) + (255,), anchor="mm")
        self.pill_row(self.info_pills(e), p, W, u(672), canvas)

    def render_entry(self, e, bg_path, groups, style="rail", opts=None, menu=None):
        """Per-entry scene (kernel / rescue / advanced): bg + cookie + hints + hero + info pills + style furniture."""
        opts = opts or {}; p = self.pal[e["key"]]; sc = Image.open(bg_path).convert("RGBA")
        self.decorate(sc, p, opts); self.hero(sc, e, p)
        self.draw_rail(sc, p, groups, e["key"]); return sc.convert("RGB")
    def render_class(self, key, icon_path, groups, style="rail", opts=None, menu=None):
        """Class-level scene (plain entries and fallbacks): the build-time hero scene + cookie + hints + style furniture."""
        opts = opts or {}; p = self.pal[key]; sc = Image.open(icon_path).convert("RGBA")
        self.decorate(sc, p, opts); self.draw_rail(sc, p, groups, key); return sc.convert("RGB")
