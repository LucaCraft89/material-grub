"""Live preview: the scene of one boot entry drawn from the GUI's unsaved draft (style, colours, names, icons, order), as PNG bytes.
It reuses the real renderer (mgscenes), the same overrides code as the apply step (mgcustom) and cmd_scenes.entry_scene, so what the preview
shows is what the apply step bakes. Pillow + stdlib."""

import copy
import io
import json
import tempfile
import threading
from pathlib import Path

import cmd_scenes
import mgcustom
import mgoverrides
import mgpalette
import mgscenes
from PIL import Image

ASPECTS = {
    "16x9": 1920,
    "16x10": 1728,
    "21x9": 2560,
    "32x9": 3840,
}  # design width at 1080 high (scripts/build_theme.py)


class Previewer:
    """One per server: keeps the panel cache between requests and renders one at a time (Pillow is cheap, the fonts are not thread-safe to share)."""

    def __init__(self, pkg):
        self.pkg = Path(pkg)
        self.lock = threading.Lock()
        self.tmp = tempfile.TemporaryDirectory(prefix="mg-gui-preview-")
        self.classes = json.loads((self.pkg / "classes.json").read_text())
        self.subs = (
            json.loads((self.pkg / "subtitles.json").read_text()) if (self.pkg / "subtitles.json").is_file() else {}
        )
        self._pal = {}
        self._cache = {}

    def close(self):
        self.tmp.cleanup()

    def palettes(self, dark, baked):
        """palettes.json recomputed for the dark or light scheme when it is not the baked one (the preview can show both)."""
        if (baked == "dark") == dark:
            return None
        if dark not in self._pal:
            base = json.loads((self.pkg / "palettes.json").read_text())
            self._pal[dark] = {k: {"seed": v["seed"], **mgpalette.scheme(v["seed"], dark)} for k, v in base.items()}
        return self._pal[dark]

    def render(self, entries, menu, draft, cls, dark=True, scale=0.5, aspect="16x9", icon_dir=None):
        """PNG bytes of the scene shown while the entry with class `cls` is selected. `draft` = {conf, overrides} already validated."""
        if aspect not in ASPECTS:
            raise ValueError("unknown aspect " + aspect)
        scale = min(1.0, max(0.25, float(scale)))
        H = round(1080 * scale)
        size = (round(ASPECTS[aspect] * scale), H)
        ov = draft["overrides"]
        conf = draft["conf"]
        style = conf.get("STYLE", "rail")
        opts = {"cookie": conf.get("COOKIE", "on") == "on", "hints": conf.get("HINTS", "on") == "on", "shape": "cookie"}
        with self.lock:
            ents = copy.deepcopy(entries)
            R = mgscenes.Renderer(self.pkg, H, light=not dark)
            sch = (self.pkg / "scheme.txt").read_text().strip() if (self.pkg / "scheme.txt").is_file() else "dark"
            alt = self.palettes(dark, sch)
            if alt:
                R.pal = copy.deepcopy(alt)
            if conf.get("COOKIE", "on") == "on" and conf.get("LOGO", "on") == "on":
                if "logo" not in self._cache:
                    self._cache["logo"] = {}
                lg = self._cache["logo"]
                if H not in lg:
                    lg[H] = mgscenes.machine_logo(self.pkg, round(120 * H / 1080))
                R.preview_logo = lg[H]
            overlay = mgcustom.apply(
                R, ov, ents, self.pkg, aspect, size, self.classes, icon_dir=icon_dir, tmp=self.tmp.name, always=True
            )
            by_class = {e["class"]: e for e in ents}
            e = by_class.get(cls) or next(iter(by_class.values()))
            keys = cmd_scenes.rail_keys(ents)
            groups = mgscenes.groups_of(keys, ov["groups"])
            im = cmd_scenes.entry_scene(R, overlay, e, groups, style, opts, self.menu_for(ents, menu, ov), by_class)
            out = io.BytesIO()
            im.convert("RGB").save(out, "PNG")
            return out.getvalue()

    @staticmethod
    def menu_for(entries, menu, ov):
        """The menu levels with the top level in the draft's order, so the list and clean styles show what the apply step will."""
        by_class = {e["class"]: e for e in entries}
        out = []
        for lv in menu or []:
            items = [by_class[c] for c in lv["items"] if c in by_class]
            if lv.get("level") == "top" and (ov["order"] or ov["groups"]):
                names = list(ov["groups"]) + [n for n in mgoverrides.GROUPS if n not in ov["groups"]]
                items = mgoverrides.sort_order(ov, items)
                if ov["groups"]:
                    items = sorted(items, key=lambda e: names.index(_group(e["key"])))
            out.append({**lv, "items": [e["class"] for e in items]})
        return out


def _group(key):
    base = mgscenes.base_key(key)
    return "windows" if base in mgscenes.WIN else "system" if base in mgscenes.SYS else "linux"


def thumbnail(png, width):
    im = Image.open(io.BytesIO(png))
    im.thumbnail((width, width))
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()
