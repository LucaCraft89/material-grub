"""Render per-entry scenes (hero, info pills, cookie, key hints, style furniture) into the active theme. Needs Pillow.
Style and options come from /etc/material-grub.conf (STYLE, COOKIE, HINTS); the drawing code is in mgscenes.py.
usage: material-grub-scenes --theme DIR [--state entries.json] [--pkg DIR]"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import mgoverrides
import mgrub
import mgsafe


def arg(n, d=None):
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d


import os


def main():
    global mgcustom
    try:
        import mgcustom
        import mgscenes
        from PIL import Image
    except ImportError:
        print("material-grub: Pillow missing, per-entry scenes disabled", file=sys.stderr)
        sys.exit(0)
    pkg = Path(arg("--pkg", "/usr/share/material-grub"))
    theme = Path(arg("--theme"))
    state = Path(arg("--state", str(mgsafe.state_dir() / "entries.json")))
    entries = json.loads(state.read_text()) if state.exists() else []
    menu = json.loads(state.with_name("menu.json").read_text()) if state.with_name("menu.json").exists() else []
    classes = json.loads((pkg / "classes.json").read_text())
    conf = mgrub.load_conf()
    style = conf["STYLE"]
    opts = {
        "cookie": conf["COOKIE"] == "on",
        "hints": conf["HINTS"] == "on",
        "shape": os.environ.get("MG_LIST_SHAPE", "cookie"),
    }  # shape: prototype knob
    aspect = (theme / ".aspect").read_text().strip()
    bgs = sorted((pkg / "scenes" / aspect / "bg").glob("*.png"))
    scene_size = Image.open(bgs[0]).size if bgs else (1920, 1080)
    R = mgscenes.Renderer(pkg, scene_size[1])
    R.bg_dir = pkg / "scenes" / aspect / "bg"
    ov, problems = mgoverrides.load()
    for pr in problems:
        print(f"material-grub: overrides: {pr}")
    seen = {}
    for e in (
        entries
    ):  # the same distro twice on one menu level (os-prober installs on two drives): rows and chips name the drive
        if e.get("where"):
            seen.setdefault((e["key"], e.get("level", "top")), []).append(e)
    for group in seen.values():
        if len(group) > 1:
            for e in group:
                e["dup_where"] = True
    tmp = tempfile.mkdtemp(prefix="mg-overlay-")
    try:
        overlay = mgcustom.apply(R, ov, entries, pkg, aspect, scene_size, classes, tmp=tmp)
        bake(R, ov, overlay, entries, menu, classes, theme, style, opts)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def rail_keys(entries):
    """The keys the rail shows, top-level entries first (one slot per key)."""
    keys = []
    tops = [e for e in entries if e.get("level", "top") == "top"] or entries
    for e in tops + entries:
        if e["key"] not in keys:
            keys.append(e["key"])
    return keys


def entry_scene(R, overlay, e, groups, style, opts, menu, by_class):
    """The scene (PIL image) shown while entry `e` is selected: the same drawing for the real bake and for the GUI's live preview."""
    import mgscenes

    if (
        e["kind"] == "plain" and style == "rail"
    ):  # plain entries in the rail style are the class scene with their own slot lit
        return R.render_class(e["key"], overlay.icon(e["key"]), groups, "rail", opts, menu, rail_sel=e["key"])
    plain_hero = e["kind"] == "plain" and style not in mgscenes.LISTY
    src = overlay.icon(e["key"]) if plain_hero else overlay.bg(e["key"])
    return R.render_entry(e, src, groups, style, opts, menu, by_class)


def bake(R, ov, overlay, entries, menu, classes, theme, style, opts):
    import mgscenes

    by_class = {e["class"]: e for e in entries if "class" in e}
    if style not in mgscenes.STYLES:
        print(f"material-grub: style '{style}' is not available yet, drawing 'rail'")
        style = "rail"
    keys = rail_keys(entries)
    groups = mgscenes.groups_of(keys, ov["groups"])
    if not groups:
        sys.exit(0)
    done = 0
    for k in dict.fromkeys(
        mgscenes.base_key(k) for k in keys
    ):  # class scenes: used by plain entries (Windows, Firmware...) and as fallbacks
        first = theme / "icons" / f"{classes[k][0]}.png"
        R.render_class(
            k,
            overlay.bg(k) if style in mgscenes.LISTY else overlay.icon(k),
            groups,
            style,
            opts,
            menu,
        ).save(first)
        for a in classes[k][1:]:
            shutil.copyfile(first, theme / "icons" / f"{a}.png")
    per_entry = ("kernel", "rescue", "advanced") + (
        ("plain",) if style != "rail" else ()
    )  # clean/list: neighbours differ per entry, so plain entries need their own scene too
    for e in entries:
        if e.get("class", "").startswith("mg_") and (e["kind"] in per_entry or e.get("orig_key")):
            entry_scene(R, overlay, e, groups, style, opts, menu, by_class).save(theme / "icons" / f"{e['class']}.png")
            done += 1
    print(
        f"material-grub: {done} entry scenes + {len(keys)} class scenes baked; style {style}; rail: {' | '.join(' '.join(g) for g in groups)}"
    )
