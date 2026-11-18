"""Scene renderer shared by material-grub-scenes (config time), scripts/ (distro gallery) and, later, other targets. Pillow + stdlib only.
Importable without side effects: build a Renderer, then call its draw_* / render_entry methods.
Every coordinate is a 1080-high design value passed through u(), which scales with the scene height."""

import json
import math
import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIN, SYS = {"windows10", "windows11"}, {"firmware", "reboot", "shutdown"}
STYLES = ("rail", "clean", "list", "split")
LISTY = (
    "list",
    "split",
)  # styles that bake a list into the scene; `split` is `list` with the hero on the left and the list on the right


def hexc(c):
    return tuple(int(c[i : i + 2], 16) for i in (1, 3, 5))


def poly_mask(size, fn, ss=3, n=720):
    S = size * ss
    im = Image.new("L", (S, S), 0)
    c = S / 2
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        r = fn(t) * c
        pts.append((c + r * math.cos(t), c + r * math.sin(t)))
    ImageDraw.Draw(im).polygon(pts, fill=255)
    return im.resize((size, size), Image.LANCZOS)


SHAPES = {  # same outlines as scripts/render_scene.py (the build-time panels)
    "flower": lambda t: 0.80 + 0.17 * math.cos(8 * t),
    "cookie": lambda t: 0.90 + 0.06 * math.cos(9 * t),
    "sunny": lambda t: 0.82 + 0.15 * (abs(math.cos(6 * t)) ** 0.6),
    "clover": lambda t: 0.62 + 0.36 * abs(math.cos(2 * t)) ** 0.7,
}


def groups_of(keys):
    return [
        g
        for g in (
            [k for k in keys if k not in WIN | SYS],
            [k for k in keys if k in WIN],
            [k for k in ("firmware", "reboot", "shutdown") if k in keys],
        )
        if g
    ]


class Renderer:
    def __init__(self, pkg, height=1080, light=None, font_path=None):
        self.pkg = Path(pkg)
        self.H = height
        self.S = height / 1080
        self.SS = 3 if self.S <= 1 else 2  # supersampling of rail/pill shapes (cheaper on the 2160-high sets)
        self.pal = json.loads((self.pkg / "palettes.json").read_text())
        self.titles = json.loads((self.pkg / "titles.json").read_text())
        sch = self.pkg / "scheme.txt"
        self.light = light if light is not None else (sch.exists() and sch.read_text().strip() == "light")
        self.font_path = str(font_path or self.pkg / "fonts/GoogleSansFlex-VF.ttf")
        self._g, self._nd, self._fb = {}, {}, {}
        self.logos = {}  # catalog key -> full-colour logo (PIL image on a white background): drawn on a white card instead of the glyph in a cookie (Ventoy: PNLug)
        self.galias = {}  # pseudo entry key -> glyph name (Ventoy's own menus borrow glyphs and palettes of catalog entries)
        self.hint_labels = [
            "Arrows  select",
            "Enter  boot",
            "E  edit",
            "C  console",
        ]  # the GRUB keys; other targets (Ventoy) replace the list
        u = self.u
        self.SLOT, self.GAP, self.DIV, self.PADV, self.RW, self.LM = (
            u(72),
            u(10),
            u(30),
            u(22),
            u(100),
            u(52),
        )  # rail metrics

    def u(self, v):
        return round(v * self.S)

    # ---- fonts / glyphs ----
    def font(self, size, wght=500, wdth=100, rond=0):
        f = ImageFont.truetype(self.font_path, size)
        want = {"optical": size * 0.75, "width": wdth, "weight": wght, "roundness": rond, "grade": 0, "slant": 0}
        vals = []
        for ax in f.get_variation_axes():  # by name: works with any version of the font (GRAD removed in v5)
            n = ax["name"].decode() if isinstance(ax["name"], bytes) else ax["name"]
            v = next((want[k] for k in want if k in n.lower()), ax["default"])
            vals.append(min(max(v, ax["minimum"]), ax["maximum"]))
        f.set_variation_by_axes(vals)
        return f

    def _render(self, f, c):
        im = Image.new("L", (96, 96))
        ImageDraw.Draw(im).text((8, 8), c, font=f, fill=255)
        return im.tobytes()

    def has_glyphs(
        self, f, text
    ):  # a character the font lacks renders as its .notdef glyph; compare with a codepoint no font maps
        nd = self._render(
            f, "\U0010ffff"
        )  # not cached: the .notdef bitmap depends on size and variation, and id(f) is reused after garbage collection
        return all(c.isspace() or self._render(f, c) != nd for c in text)

    def fallback_font(self, text, size):
        """Google Sans Flex is Latin only: for pills with other scripts use any installed font that has the characters (fontconfig, else common paths)."""
        want = sorted({c for c in text if ord(c) > 0x24F})[:6]
        key = tuple(want)
        if key not in self._fb:
            cands = []
            try:
                cands.append(
                    subprocess.run(
                        ["fc-match", "-f", "%{file}", "sans:charset=" + " ".join(f"{ord(c):x}" for c in want)],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    ).stdout.strip()
                )
            except Exception:
                pass
            cands += [
                "/usr/share/fonts/noto/NotoSans-Regular.ttf",
                "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
                "/usr/share/fonts/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/TTF/DejaVuSans.ttf",
            ]
            self._fb[key] = next((c for c in cands if c and os.path.exists(c)), None)
        if not self._fb[key]:
            return None
        f = ImageFont.truetype(self._fb[key], size)
        try:  # variable fallback fonts (Noto VF) default to their lightest weight; match the pills' medium weight
            axes = f.get_variation_axes()
            f.set_variation_by_axes(
                [min(max(560, a["minimum"]), a["maximum"]) if "eight" in str(a["name"]) else a["default"] for a in axes]
            )
        except Exception:
            pass
        return f

    def text_font(self, text, size, wght=500, wdth=100, rond=0):
        f = self.font(size, wght, wdth, rond)
        if all(ord(c) < 0x250 for c in text) or self.has_glyphs(f, text):
            return f
        return self.fallback_font(text, size) or f

    def glyph(self, name, size, color):
        name = self.galias.get(name, name)
        a = self._g.setdefault(name, Image.open(self.pkg / "glyphs" / f"{name}.png").convert("RGBA").getchannel("A"))
        im = Image.new("RGBA", (size, size), color)
        im.putalpha(a.resize((size, size), Image.LANCZOS))
        return im

    # ---- primitives ----
    def rrect(self, w, h, r, fill):
        SS = self.SS
        im = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
        ImageDraw.Draw(im).rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], radius=r * SS, fill=fill)
        return im.resize((w, h), Image.LANCZOS)

    @staticmethod
    def paste_c(dst, src, cx, cy):
        dst.alpha_composite(src, (round(cx - src.width / 2), round(cy - src.height / 2)))

    def shape(self, name, size, color):
        """An M3 shape (cookie, flower, sunny, clover) filled with `color`; 3x supersampled like the build-time panels."""
        im = Image.new("RGBA", (size, size), hexc(color) + (255,))
        im.putalpha(poly_mask(size, SHAPES[name]))
        return im

    def pill(self, text, p, style="plain", icon=None, h=None):
        u = self.u
        h = h or u(58)
        f = self.text_font(text, u(28), 560, 104)
        tw = int(f.getlength(text))
        ic = u(30) if icon else 0
        w = u(28) * 2 + tw + (ic + u(10) if icon else 0)
        bg, fg = (
            (hexc(p["primaryContainer"]), hexc(p["onPrimaryContainer"]))
            if style == "accent"
            else (hexc(p["surfaceContainerHigh"]), hexc(p["onSurface"]))
        )
        im = self.rrect(w, h, h // 2, bg + (255,))
        d = ImageDraw.Draw(im)
        x = u(28)
        if icon:
            im.alpha_composite(self.glyph(icon, ic, fg + (255,)), (x, (h - ic) // 2))
            x += ic + u(10)
        d.text((x, h // 2 + u(1)), text, font=f, fill=fg + (255,), anchor="lm")
        return im

    def pill_row(self, items, p, W, y, canvas, cx=None, maxw=None):
        """Info pills in a row centred on cx (default: the middle of the scene), dropping the last ones that do not fit in maxw."""
        pills = [self.pill(*i[:1], p, *i[1:]) for i in items]
        g = self.u(14)
        maxw = maxw or W * 0.78
        while pills and sum(x.width for x in pills) + g * (len(pills) - 1) > maxw:
            pills.pop()
        tot = sum(x.width for x in pills) + g * (len(pills) - 1)
        x = (cx if cx is not None else W // 2) - tot // 2
        for pl in pills:
            canvas.alpha_composite(pl, (x, y))
            x += pl.width + g

    # ---- text model ----
    @staticmethod
    def info_pills(e):
        kind = e["kind"]
        os_ = " ".join(x for x in (e.get("os"), e.get("osver")) if x)
        if kind == "kernel":
            out = [(e["kver"], "accent", "kernel")] if e.get("kver") else []
            if os_:
                out.append((os_, "plain", None))
            if e.get(
                "where"
            ):  # os-prober entries: tells two installs of the same distro apart (kept before the edition: a full row drops the last pills)
                out.append((e["where"], "plain", None))
            if e.get("edition"):
                out.append((e["edition"], "plain", None))
            if e.get("default"):
                out.append(("Default", "plain", "tag"))
            return out or [(e["title"], "plain", None)]
        if kind == "rescue":
            out = [("Rescue mode", "accent", "wrench")]
            if e.get("kver") and not e["kver"].startswith("0-rescue"):
                out.append((e["kver"], "plain", "kernel"))
            if os_:
                out.append((os_, "plain", None))
            if e.get("where"):
                out.append((e["where"], "plain", None))
            return out
        if kind == "advanced":
            out = [("Advanced options", "accent", "gear")]
            if e.get("count"):
                out.append((f"{e['count']} more entries", "plain", None))
            return out
        if e.get("where"):  # Windows and other foreign systems found by os-prober
            return [(e["where"], "plain", None)]
        return []

    def title_for(self, e):
        return {"advanced": "Advanced", "rescue": "Rescue"}.get(e["kind"]) or self.titles.get(e["key"], e["key"])

    # ---- cookie (top-right) and key hints: drawn at config time, so they are runtime options ----
    def draw_cookie(self, canvas, p):
        u = self.u
        W = canvas.width
        c = self.shape("cookie", u(230), p["primaryContainer"])
        canvas.alpha_composite(
            c, (int(W - u(150 - self.cookie_off[0]) - c.width / 2), int(u(140 + self.cookie_off[1]) - c.height / 2))
        )

    def key_hints(self, p):
        u = self.u
        f = self.font(u(24), 520, 105)
        hh = u(46)
        parts = []
        for s in self.hint_labels:
            w = int(f.getlength(s)) + u(44)
            m = Image.new("L", (w * 3, hh * 3), 0)
            ImageDraw.Draw(m).rounded_rectangle([0, 0, w * 3 - 1, hh * 3 - 1], radius=hh * 3 // 2, fill=255)
            im = Image.new("RGBA", (w, hh), hexc(p["surfaceContainerHigh"]) + (255,))
            im.putalpha(m.resize((w, hh), Image.LANCZOS))
            ImageDraw.Draw(im).text((w // 2, hh // 2 + u(1)), s, font=f, fill=hexc(p["onSurfaceVariant"]), anchor="mm")
            parts.append(im)
        gap = u(14)
        tot = sum(i.width for i in parts) + gap * (len(parts) - 1)
        out = Image.new("RGBA", (tot, hh), (0, 0, 0, 0))
        x = 0
        for i in parts:
            out.alpha_composite(i, (x, 0))
            x += i.width + gap
        return out

    def draw_hints(self, canvas, p):
        hint = self.key_hints(p)
        canvas.alpha_composite(hint, ((canvas.width - hint.width) // 2, canvas.height - self.u(120)))

    # ---- rail ----
    def draw_rail(self, canvas, p, groups, sel):
        u, SS, SLOT, GAP, DIV, PADV, RW, LM = (
            self.u,
            self.SS,
            self.SLOT,
            self.GAP,
            self.DIV,
            self.PADV,
            self.RW,
            self.LM,
        )
        n = sum(map(len, groups))
        Hr = n * SLOT + (n - len(groups)) * GAP + (len(groups) - 1) * DIV + 2 * PADV
        W, H = canvas.size
        top = (H - Hr) // 2
        layer = Image.new("RGBA", (RW * SS, Hr * SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.rounded_rectangle(
            [0, 0, RW * SS - 1, Hr * SS - 1], radius=RW * SS // 2, fill=hexc(p["surfaceContainerHigh"]) + (255,)
        )
        y = PADV
        slots = []
        for gi, g in enumerate(groups):
            if gi:
                ly = y + DIV // 2 - GAP // 2
                d.rounded_rectangle(
                    [(RW // 2 - u(14)) * SS, ly * SS, (RW // 2 + u(14)) * SS, (ly + u(2)) * SS],
                    radius=SS,
                    fill=hexc(p["outline"]) + (150,),
                )
                y += DIV - GAP
            for k in g:
                slots.append((k, y))
                y += SLOT + GAP
        for k, sy in slots:
            if k == sel:
                d.rounded_rectangle(
                    [(RW - SLOT) // 2 * SS, sy * SS, ((RW + SLOT) // 2) * SS - 1, (sy + SLOT) * SS - 1],
                    radius=u(26) * SS,
                    fill=hexc(p["primaryContainer"]) + (255,),
                )
        layer = layer.resize((RW, Hr), Image.LANCZOS)
        for k, sy in slots:
            layer.alpha_composite(
                self.glyph(
                    k,
                    u(40),
                    hexc(p["onPrimaryContainer"]) + (255,)
                    if k == sel
                    else (hexc(p["onSurfaceVariant"]) + (255,) if self.light else (244, 244, 247, 235)),
                ),
                ((RW - u(40)) // 2, sy + (SLOT - u(40)) // 2),
            )
        canvas.alpha_composite(layer, (LM, top))

    # ---- scenes ----
    def decorate(self, canvas, p, opts):
        """Runtime overlays that every style shares: top-right cookie (COOKIE) and key-hint pills (HINTS)."""
        if opts.get("cookie", True):
            self.draw_cookie(canvas, p)
        if opts.get("hints", True):
            self.draw_hints(canvas, p)

    def hero(self, canvas, e, p, tsz0=150):
        u = self.u
        W = canvas.width
        cx = W // 2
        paste_c = self.paste_c
        paste_c(canvas, self.rrect(u(600), u(320), u(160), hexc(p["surfaceContainerHigh"]) + (255,)), cx, u(360))
        logo = self.logos.get(e["key"])
        paste_c(
            canvas,
            self.rrect(u(560), u(280), u(140), (255, 255, 255, 255) if logo else hexc(p["primaryContainer"]) + (255,)),
            cx,
            u(360),
        )
        ink = hexc(p["onPrimaryContainer"]) + (255,)
        acc = {"advanced": "gear", "rescue": "wrench"}.get(e["kind"])
        if logo:
            paste_c(canvas, self.fit_logo(logo, u(440)), cx, u(360))
        elif acc:
            paste_c(canvas, self.glyph(e["key"], u(190), ink), cx - u(92), u(360))
            paste_c(canvas, self.glyph(acc, u(120), ink), cx + u(140), u(360))
        else:
            paste_c(canvas, self.glyph(e["key"], u(230), ink), cx, u(360))
        d = ImageDraw.Draw(canvas)
        title = self.title_for(e)
        tsz = u(tsz0)
        while tsz > u(60) and self.font(tsz, 800, 135, 60).getlength(title) > W * 0.62:
            tsz -= u(6)
        d.text((cx, u(590)), title, font=self.font(tsz, 800, 135, 60), fill=hexc(p["primary"]) + (255,), anchor="mm")
        self.pill_row(self.info_pills(e), p, W, u(672), canvas)

    # ---- clean style: the first version's look (a big panel for the entry, the neighbours peek in above and below, label chips on the panel edges) ----
    CLEAN = dict(margin=24, top=96, ph=888, gap=12, radius=64, chip_h=52, chip_pad=16)

    def label_for(self, e):
        """Chip / list-row label: an explicit `label` (Ventoy: the raw ISO file name), else the kernel version for kernels inside a submenu, else the usual title."""
        if e.get("label"):
            return e["label"]
        if e["kind"] == "kernel" and e.get("level") == "adv" and e.get("kver"):
            return e["kver"]
        if e.get("dup_where") and e.get("where"):  # two installs of one distro: the drive tells the rows apart
            return f"{self.title_for(e)} ({e['where'].rsplit('/', 1)[-1]})"
        return self.title_for(e)

    @staticmethod
    def fit_label(label, f, maxw):
        """Cut `label` with an ellipsis so it is at most `maxw` pixels wide in font `f`."""
        if f.getlength(label) <= maxw:
            return label
        while len(label) > 1 and f.getlength(label + "\u2026") > maxw:
            label = label[:-1]
        return label.rstrip() + "\u2026"

    def chip(self, e, p, h=None):
        u = self.u
        h = h or u(self.CLEAN["chip_h"])
        f = self.text_font(self.label_for(e), u(26), 560, 105)
        label = self.fit_label(self.label_for(e), f, u(900))
        icons = (
            [e["key"]]
            + (["iso"] if getattr(self, "chip_disc", False) else [])
            + ([{"advanced": "gear", "rescue": "wrench"}[e["kind"]]] if e["kind"] in ("advanced", "rescue") else [])
        )
        ic = h - u(24)
        pad = u(22)
        w = pad * 2 + int(f.getlength(label)) + len(icons) * (ic + u(10))
        im = self.rrect(w, h, h // 2, hexc(p["surfaceContainerHigh"]) + (255,))
        x = pad
        for g in icons:
            im.alpha_composite(self.glyph(g, ic, hexc(p["primary"]) + (255,)), (x, (h - ic) // 2))
            x += ic + u(10)
        ImageDraw.Draw(im).text((x, h // 2 + u(1)), label, font=f, fill=hexc(p["onSurface"]) + (255,), anchor="lm")
        return im

    def panel_from(self, scene, ctx):
        """Crop the panel region out of a full-screen scene and round its corners (content keeps its absolute position)."""
        m, t, ph = ctx
        pw = scene.width - 2 * m
        im = scene.crop((m, t, m + pw, t + ph)).convert("RGBA")
        mask = self.rrect(pw, ph, self.u(self.CLEAN["radius"]), (255, 255, 255, 255)).getchannel("A")
        im.putalpha(mask)
        return im

    @staticmethod
    def paste_clipped(canvas, im, x, y):
        """alpha_composite that tolerates negative / overflowing positions."""
        x0, y0 = max(0, -x), max(0, -y)
        x1, y1 = min(im.width, canvas.width - x), min(im.height, canvas.height - y)
        if x1 > x0 and y1 > y0:
            canvas.alpha_composite(im.crop((x0, y0, x1, y1)), (x + x0, y + y0))

    def render_clean(self, e, scene, prev, nxt, opts):
        """`scene`: the full-screen scene of the entry (bg + hero). prev / nxt: neighbour entries (or None)."""
        u = self.u
        c = self.CLEAN
        m, t, ph, gap = (u(c[k]) for k in ("margin", "top", "ph", "gap"))
        W, H = scene.size
        base = self.pal.get("base", self.pal[e["key"]])
        canvas = Image.new("RGBA", (W, H), hexc(base["surface"]) + (255,))
        ctx = (m, t, ph)
        cp = u(c["chip_pad"])
        for ne, y in ((prev, t - gap - ph), (nxt, t + ph + gap)):
            if ne is None:
                continue
            np_ = self.pal[ne["key"]]
            pn = self.panel_from(Image.open(self.bg_dir / f"{ne['key']}.png").convert("RGBA"), ctx)
            ch = self.chip(ne, np_)
            for cy in (cp, ph - ch.height - cp):
                pn.alpha_composite(ch, ((pn.width - ch.width) // 2, cy))
            self.paste_clipped(canvas, pn, m, y)
        p = self.pal[e["key"]]
        pn = self.panel_from(scene, ctx)
        ch = self.chip(e, p)
        for cy in (cp, ph - ch.height - cp):
            pn.alpha_composite(ch, ((pn.width - ch.width) // 2, cy))
        canvas.alpha_composite(pn, (m, t))
        if opts.get("cookie", True):
            ck = self.shape("cookie", u(230), p["primaryContainer"])
            canvas.alpha_composite(ck, (int(W - m - u(150) - ck.width / 2), int(t + u(140) - ck.height / 2)))
        if opts.get("hints", True):
            hint = self.key_hints(p)
            canvas.alpha_composite(hint, ((W - hint.width) // 2, t + ph - cp - ch.height - u(12) - hint.height))
        return canvas

    @staticmethod
    def neighbours(menu, by_class, e, wrap=True):
        """(previous, next) entries in the same menu level, as GRUB lists them; None where there is none (no menu info, single entry, no wrap at the ends)."""
        for lv in menu or []:
            if e.get("class") in lv["items"]:
                items = [by_class[c] for c in lv["items"] if c in by_class]
                n = len(items)
                i = next(k for k, x in enumerate(items) if x["class"] == e["class"])
                if n < 2:
                    return None, None
                prev = items[i - 1] if (wrap or i > 0) else None
                nxt = items[(i + 1) % n] if (wrap or i < n - 1) else None
                return prev, nxt
        return None, None

    # ---- list style: the whole menu level is drawn into the scene, centred, with the selected entry highlighted ----
    LIST = dict(col=640, row=76, gap=12, div=30, top=110, bottom=840, more_h=40, shape_glyph=40)

    def _group(self, key):
        return 2 if key in SYS else 1 if key in WIN else 0

    def list_label(self, e):
        return {"advanced": "Advanced options", "rescue": "Rescue"}.get(e["kind"]) or self.label_for(e)

    def list_window(self, items, sel):
        """Choose the largest window of rows around `sel` that fits the available height. Returns (start, end, height)."""
        u = self.u
        L = self.LIST
        avail = u(L["bottom"] - L["top"])
        row, gap, div = u(L["row"]), u(L["gap"]), u(L["div"])
        more = u(L["more_h"]) + u(10)

        def height(a, b):
            h = sum(row for _ in range(a, b)) + sum(
                div if self._group(items[k]["key"]) != self._group(items[k - 1]["key"]) else gap
                for k in range(a + 1, b)
            )
            return h + (more if a > 0 else 0) + (more if b < len(items) else 0)

        n = len(items)
        for k in range(n, 0, -1):
            a = min(max(sel - k // 2, 0), n - k)
            b = a + k
            if height(a, b) <= avail:
                return a, b, height(a, b)
        return sel, sel + 1, row

    def draw_list(self, canvas, p, items, sel, opts, x0=None):
        u = self.u
        L = self.LIST
        W, H = canvas.size
        row, gap, div = u(L["row"]), u(L["gap"]), u(L["div"])
        col = u(L["col"])
        a, b, h = self.list_window(items, sel or 0)
        x0 = (W - col) // 2 if x0 is None else x0
        mid = x0 + col // 2  # sel=None: nothing highlighted (fallback scene for entries that arrived after install)
        top = max(u(L["top"]), min((H - h) // 2, u(L["bottom"]) - h))
        y = top
        shape = opts.get("shape", "cookie")

        def more(n, y):
            im = self.pill(f"+{n} more", p, "plain", None, h=u(L["more_h"]))
            canvas.alpha_composite(im, (mid - im.width // 2, y))
            return y + im.height + u(10)

        if a > 0:
            y = more(a, y)
        d = ImageDraw.Draw(canvas)
        for k in range(a, b):
            e = items[k]
            if k > a:
                if self._group(e["key"]) != self._group(items[k - 1]["key"]):
                    ly = y + div // 2 - gap // 2 - u(1)
                    d.rounded_rectangle(
                        [mid - u(60), ly, mid + u(60), ly + u(2)], radius=u(1), fill=hexc(p["outline"]) + (150,)
                    )
                    y += div
                else:
                    y += gap
            on = sel is not None and k == sel
            sh = self.shape(shape, row, p["primary"] if on else p["surfaceContainerHigh"])
            canvas.alpha_composite(sh, (x0, y))
            g = self.glyph(e["key"], u(L["shape_glyph"]), hexc(p["onPrimary"] if on else p["primary"]) + (255,))
            self.paste_c(canvas, g, x0 + row / 2, y + row / 2)
            ph = u(64)
            pw = col - row - u(14)
            pill = self._list_pill(self.list_label(e), e, p, on, pw, ph)
            canvas.alpha_composite(pill, (x0 + row + u(14), y + (row - ph) // 2))
            y += row
        if b < len(items):
            more(len(items) - b, y + u(10))

    def _list_pill(self, label, e, p, on, w, h):
        u = self.u
        bg, fg = (p["primaryContainer"], p["onPrimaryContainer"]) if on else (p["surfaceContainerHigh"], p["onSurface"])
        acc = {"advanced": "gear", "rescue": "wrench"}.get(e["kind"])
        size = u(28)
        f = self.text_font(label, size, 560, 104)
        ic = u(30) if acc else 0
        room = w - u(28) * 2 - (ic + u(12) if acc else 0)
        while f.getlength(label) > room and size > u(16):
            size -= u(2)
            f = self.text_font(label, size, 560, 104)
        label = self.fit_label(label, f, room)
        im = self.rrect(w, h, h // 2, hexc(bg) + (255,))
        x = u(28)
        if acc:
            im.alpha_composite(self.glyph(acc, ic, hexc(fg) + (255,)), (x, (h - ic) // 2))
            x += ic + u(12)  # second icon right before the name, name shifted right
        ImageDraw.Draw(im).text((x, h // 2 + u(1)), label, font=f, fill=hexc(fg) + (255,), anchor="lm")
        return im

    @staticmethod
    def level_items(menu, by_class, e):
        """(siblings in the entry's menu level, index of e); just [e] without menu info."""
        for lv in menu or []:
            if e.get("class") in lv["items"]:
                items = [by_class[c] for c in lv["items"] if c in by_class]
                return items, next(k for k, x in enumerate(items) if x["class"] == e["class"])
        return [e], 0

    cookie_off = (
        0,
        0,
    )  # design-px shift of the top-right cookie (Ventoy `clean`: its theme moves the logo with the cookie of the panel, so list scenes in that theme follow)
    chip_disc = (
        False  # Ventoy full-screen scenes: a disc icon after the distro logo in the chips (the entry is a disk image)
    )
    bg_dir = None  # set by the caller: <pkg>/scenes/<aspect>/bg (the neighbours' panels in `clean` come from there)

    def render_entry(self, e, bg_path, groups, style="rail", opts=None, menu=None, by_class=None):
        """Per-entry scene. Kernel / rescue / advanced: bg + hero + info pills. Plain entries in clean/list styles pass their class hero scene as bg_path."""
        opts = opts or {}
        p = self.pal[e["key"]]
        sc = Image.open(bg_path).convert("RGBA")
        if style in LISTY:
            items, sel = self.level_items(menu, by_class or {}, e)
            self.decorate(sc, p, opts)
            if style == "split":
                self.draw_side_hero(
                    sc, e["key"], p, opts, {"advanced": "gear", "rescue": "wrench"}.get(e["kind"]), self.title_for(e)
                )
            self.draw_list(sc, p, items, sel, opts, self.split_x(sc.width) if style == "split" else None)
            # the info pills of the selected entry: under the hero in split, under the list in list
            u = self.u
            if style == "split":
                self.pill_row(
                    self.info_pills(e), p, sc.width, u(818), sc, cx=round(sc.width * 0.25), maxw=sc.width * 0.42
                )
            else:
                self.pill_row(self.info_pills(e), p, sc.width, u(880), sc)
            return sc.convert("RGB")
        if e["kind"] != "plain":
            self.hero(sc, e, p)
        if style == "clean":
            prev, nxt = self.neighbours(menu, by_class or {}, e, opts.get("wrap", True))
            return self.render_clean(e, sc, prev, nxt, opts).convert("RGB")
        self.decorate(sc, p, opts)
        self.draw_rail(sc, p, groups, e["key"])
        return sc.convert("RGB")

    def render_list_fallback(self, key, bg_path, items, opts=None):
        """`list` scene with the whole menu level and no highlight: shown for an entry the scene set does not know (an ISO added after install)."""
        opts = opts or {}
        p = self.pal[key]
        sc = Image.open(bg_path).convert("RGBA")
        self.decorate(sc, p, opts)
        self.draw_list(sc, p, items, None, opts)
        return sc.convert("RGB")

    @staticmethod
    def split_x(W):
        return round(W * 0.47)  # left edge of the list in `split` (and in the dynamic Ventoy list)

    def fit_logo(self, logo, w):
        """A full-colour logo scaled to width `w` (RGBA)."""
        return logo.convert("RGBA").resize((w, max(1, round(logo.height * w / logo.width))), Image.LANCZOS)

    def draw_arrows(self, canvas, p):
        """Two small arrows (up, down) in a rounded container on the left: the only hint of the full-screen picker that more entries are above / below."""
        u = self.u
        RW, SLOT, PADV, LM = self.RW, self.SLOT, self.PADV, self.LM
        gap = u(10)
        Hr = 2 * SLOT + gap + 2 * PADV
        W, H = canvas.size
        layer = self.rrect(RW, Hr, RW // 2, hexc(p["surfaceContainerHigh"]) + (255,))
        ink = hexc(p["primary"]) + (255,)
        gs = u(40)
        base = self.glyph("back", gs, ink)
        for i, ang in enumerate((-90, 90)):
            layer.alpha_composite(
                base.rotate(ang), ((RW - gs) // 2, PADV + i * (SLOT + gap) + (SLOT - gs) // 2)
            )  # the back arrow points left: -90 turns it up, +90 down
        canvas.alpha_composite(layer, (LM, (H - Hr) // 2))

    def draw_side_hero(self, sc, key, p, opts, acc=None, title=None):
        """The hero of `split` / the dynamic Ventoy list: the distro's glyph in a big cookie on the left (a gear / wrench next to it for Advanced / Rescue) and its name below."""
        u = self.u
        W = sc.width
        cx, cy = round(W * 0.25), u(450)
        logo = self.logos.get(key)
        if logo:
            self.paste_c(sc, self.rrect(u(480), u(270), u(64), (255, 255, 255, 255)), cx, cy)
            self.paste_c(sc, self.fit_logo(logo, u(420)), cx, cy)  # a logo with its own colours sits on a white card
        else:
            self.paste_c(sc, self.shape("cookie", u(400), p["primaryContainer"]), cx, cy)
        ink = hexc(p["onPrimaryContainer"]) + (255,)
        if logo:
            pass
        elif acc:
            self.paste_c(sc, self.glyph(key, u(150), ink), cx - u(62), cy)
            self.paste_c(sc, self.glyph(acc, u(96), ink), cx + u(88), cy)
        else:
            self.paste_c(sc, self.glyph(key, u(200), ink), cx, cy)
        title = title or self.title_for({"kind": "plain", "key": key})
        size = u(96)
        while size > u(48) and self.font(size, 800, 135, 60).getlength(title) > W * 0.38:
            size -= u(4)
        ImageDraw.Draw(sc).text(
            (cx, cy + u(290)), title, font=self.font(size, 800, 135, 60), fill=hexc(p["primary"]) + (255,), anchor="mm"
        )

    def render_list_hero(self, key, bg_path, opts=None):
        """Dynamic `list` scene (no per-file data): the distro's glyph in a cookie and its name on the left. The rows are drawn by GRUB itself (a native boot_menu), so the scene works for any ISO list."""
        opts = opts or {}
        p = self.pal[key]
        sc = Image.open(bg_path).convert("RGBA")
        self.decorate(sc, p, opts)
        self.draw_side_hero(sc, key, p, opts)
        return sc.convert("RGB")

    def render_class(self, key, icon_path, groups, style="rail", opts=None, menu=None, rail_sel=None):
        """Class-level scene (fallbacks, and plain entries in the rail style): the build-time hero scene + cookie + hints + style furniture."""
        opts = opts or {}
        p = self.pal[key]
        sc = Image.open(icon_path).convert("RGBA")
        if style == "list":
            self.decorate(sc, p, opts)
            return sc.convert("RGB")  # fallback only: the real list scenes are per entry
        if style == "split":
            return self.render_list_hero(key, icon_path, opts)
        if style == "clean":
            return self.render_clean({"key": key, "kind": "plain", "title": key}, sc, None, None, opts).convert("RGB")
        self.decorate(sc, p, opts)
        self.draw_rail(sc, p, groups, rail_sel or key)
        return sc.convert(
            "RGB"
        )  # rail_sel: the slot to highlight when the rail shows sections instead of one slot per entry
