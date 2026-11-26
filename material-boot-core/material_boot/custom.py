"""Apply the user's overrides (mgoverrides) to a scene Renderer: custom colours, names and icons, and the single-seed colour mode. Pillow + stdlib.

A customised entry gets a pseudo key '<catalog key>~<n>' (mgscenes.base_key undoes it) with its own palette, title and glyph, so the renderer
needs no special cases: it already draws everything from a key. The panels the build baked only fit the baked palettes, so for every key whose
palette changed the background and the class scene are redrawn here (Renderer.panel_scene, pixel-identical to the build) into a temporary overlay.
"""

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from . import overrides as mgoverrides  # the names of the bodies below are kept as they were in material-grub
from . import palette as mgpalette
from . import scenes as mgscenes

MASK = 512  # the size of the glyph masks in the package (glyphs/<key>.png)


def load_image(path, size=1024):
    """A user picture as an RGBA PIL image. PNG, JPEG, GIF, BMP, WEBP by Pillow; SVG through rsvg-convert or ImageMagick. None when it cannot be read."""
    path = Path(path)
    try:
        if path.suffix.lower() == ".svg":
            out = Path(tempfile.mkdtemp(prefix="mg-icon-")) / "i.png"
            try:
                rsvg = shutil.which("rsvg-convert")
                if rsvg:
                    cmd = [rsvg, "-a", "-w", str(size), "-h", str(size), "-o", str(out), str(path)]
                else:
                    im = shutil.which("magick") or shutil.which("convert")
                    if not im:
                        return None
                    cmd = [
                        im,
                        "-background",
                        "none",
                        "-density",
                        "300",
                        str(path),
                        "-resize",
                        f"{size}x{size}",
                        "PNG32:" + str(out),
                    ]
                if subprocess.run(cmd, capture_output=True, timeout=60).returncode != 0:
                    return None
                return Image.open(out).convert("RGBA").copy()
            finally:
                shutil.rmtree(out.parent, ignore_errors=True)
        im = Image.open(path)
        im.load()
        return im.convert("RGBA")
    except (OSError, ValueError, subprocess.SubprocessError, Image.DecompressionBombError):
        return None


def glyph_mask(im):
    """The one-colour mask (L, MASK x MASK) of a picture, for the places that draw a tinted glyph (rail, list rows): its alpha when it has one,
    else the dark parts of the picture."""
    im = im.copy()
    im.thumbnail((MASK, MASK), Image.LANCZOS)
    a = im.getchannel("A")
    lo, hi = a.getextrema()
    if lo == 255:  # opaque (a JPEG, a logo on white): dark means ink
        g = im.convert("L")
        a = g.point(lambda v: 255 - v)
    canvas = Image.new("L", (MASK, MASK), 0)
    canvas.paste(a, ((MASK - a.width) // 2, (MASK - a.height) // 2))
    return canvas


def on_white(im):
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return bg


class LazyDir:
    """Stands in for Renderer.bg_dir: `dir / 'fedora~1.png'` renders (once) and returns the path of that panel."""

    def __init__(self, overlay):
        self.o = overlay

    def __truediv__(self, name):
        return self.o.bg(name[:-4] if name.endswith(".png") else name)


class Overlay:
    def __init__(self, R, pkg, aspect, size, classes, subtitles, tmp, always=False):
        """always: redraw every panel here instead of using the ones the build baked (the GUI preview draws at another size). Panels are cached
        in `tmp` by their content, so a tmp dir that outlives the Overlay makes repeated previews cheap."""
        self.R, self.pkg, self.aspect, self.size, self.always = R, Path(pkg), aspect, size, always
        self.classes, self.subs, self.tmp = classes, subtitles, Path(tmp)
        self.baked = {k: dict(v) for k, v in R.pal.items()}  # what the build drew
        (self.tmp / "bg").mkdir(parents=True, exist_ok=True)
        (self.tmp / "icons").mkdir(parents=True, exist_ok=True)
        self._made = {}
        R.bg_dir = LazyDir(self)

    def changed(self, key):
        """Does this key's palette differ from what the build drew for its catalog key?"""
        return self.always or self.R.pal[key] != self.baked.get(mgscenes.base_key(key))

    def _file(self, kind, *parts):
        name = hashlib.sha1(repr((kind, self.size, parts)).encode()).hexdigest()[:20] + ".png"
        return self.tmp / ("bg" if kind == "bg" else "icons") / name

    def bg(self, key):
        base = mgscenes.base_key(key)
        if not self.changed(key):
            return self.pkg / "scenes" / self.aspect / "bg" / f"{base}.png"
        f = self._file("bg", tuple(sorted(self.R.pal[key].items())))
        if not f.exists():
            self.R.panel_scene(self.size, base, hero=False, p=self.R.pal[key]).save(f)
        return f

    def icon(self, key):
        """The class scene with the hero (rail style, plain entries)."""
        base = mgscenes.base_key(key)
        if not self.changed(key) and key == base and key not in self.R.titles_changed:
            return self.pkg / "scenes" / self.aspect / "icons" / f"{self.classes[base][0]}.png"
        title = self.R.titles.get(key) or self.R.titles.get(base, base)
        f = self._file("icon", base, title, tuple(sorted(self.R.pal[key].items())))
        if not f.exists():
            self.R.panel_scene(self.size, base, title, self.subs.get(base, ""), hero=True, p=self.R.pal[key]).save(f)
        return f


def apply(R, ov, entries, pkg, aspect, size, classes, icon_dir=None, tmp=None, log=print, always=False):
    """Customise R and `entries` (dicts from entries.json, changed in place) according to `ov`. Returns the Overlay that locates the panels."""
    pkg = Path(pkg)
    subs = {}
    if (pkg / "subtitles.json").is_file():
        import json

        subs = json.loads((pkg / "subtitles.json").read_text())
    R.titles_changed = set()
    dark = not R.light
    ov_seed = ov["seed"]
    ov_tmp = Path(tmp or tempfile.mkdtemp(prefix="mg-overlay-"))
    ov_o = Overlay(R, pkg, aspect, size, classes, subs, ov_tmp, always)
    if ov_seed["mode"] == "single":
        pal = {"seed": ov_seed["color"], **mgpalette.scheme(ov_seed["color"], dark)}
        for k in list(R.pal):
            R.pal[k] = dict(pal)
    icons = Path(icon_dir) if icon_dir else mgoverrides.icon_dir()
    n = 0
    for e in entries:
        rule = mgoverrides.rule_for(ov, e)
        if not any(k in rule for k in ("name", "color", "icon")):
            continue
        n += 1
        real = e["key"]
        pk = f"{real}~{n}"
        R.pal[pk] = (
            {"seed": rule["color"], **mgpalette.scheme(rule["color"], dark)} if "color" in rule else dict(R.pal[real])
        )
        R.galias[pk] = real
        R.titles[pk] = R.titles.get(real, real)
        icon = rule.get("icon")
        if icon and icon.startswith("file:"):
            im = load_image(icons / icon[5:])
            if im is None:
                log(f"material-grub: cannot read the icon {icons / icon[5:]}, keeping the default one")
            else:
                R.logos[pk] = on_white(im)
                R._g[pk] = glyph_mask(im)
                del R.galias[pk]  # Renderer.glyph then reads the mask above
        elif icon:
            if (pkg / "glyphs" / f"{icon}.png").is_file():
                R.galias[pk] = icon
            else:
                log(f"material-grub: there is no catalog icon '{icon}', keeping the default one")
        # a name given to a whole distro ({"key": ...}) is for its main entry: "Advanced options" and "Rescue" keep theirs
        if "name" in rule and not (e["kind"] in ("advanced", "rescue") and "key" in rule["match"]):
            R.titles[pk] = rule["name"]
            R.titles_changed.add(pk)
            e["name"] = rule["name"]
            e["label"] = rule["name"]
        e["orig_key"] = real
        e["key"] = pk
    return ov_o
