"""Render per-entry scenes (hero, info pills, cookie, key hints, style furniture) into the active theme. Needs Pillow.
Style and options come from /etc/material-grub.conf (STYLE, COOKIE, HINTS); the drawing code is in mgscenes.py.
usage: material-grub-scenes --theme DIR [--state entries.json] [--pkg DIR]"""

import json
import shutil
import sys
from pathlib import Path

import mgrub
import mgsafe


def arg(n, d=None):
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d


import os

keys = []


def main():
    try:
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
    R = mgscenes.Renderer(pkg, Image.open(bgs[0]).height if bgs else 1080)
    R.bg_dir = pkg / "scenes" / aspect / "bg"
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
    by_class = {e["class"]: e for e in entries if "class" in e}
    if style not in mgscenes.STYLES:
        print(f"material-grub: style '{style}' is not available yet, drawing 'rail'")
        style = "rail"
    tops = [e for e in entries if e.get("level", "top") == "top"] or entries
    for e in tops + entries:
        if e["key"] not in keys:
            keys.append(e["key"])
    groups = mgscenes.groups_of(keys)
    if not groups:
        sys.exit(0)
    done = 0
    for k in keys:  # class scenes: used by plain entries (Windows, Firmware...) and as fallbacks
        first = theme / "icons" / f"{classes[k][0]}.png"
        R.render_class(
            k,
            pkg
            / "scenes"
            / aspect
            / ("bg" if style in mgscenes.LISTY else "icons")
            / (f"{k}.png" if style in mgscenes.LISTY else f"{classes[k][0]}.png"),
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
        if e.get("class", "").startswith("mg_") and e["kind"] in per_entry:
            src = (
                pkg
                / "scenes"
                / aspect
                / ("icons" if e["kind"] == "plain" and style not in mgscenes.LISTY else "bg")
                / (
                    f"{classes[e['key']][0]}.png"
                    if e["kind"] == "plain" and style not in mgscenes.LISTY
                    else f"{e['key']}.png"
                )
            )
            R.render_entry(e, src, groups, style, opts, menu, by_class).save(theme / "icons" / f"{e['class']}.png")
            done += 1
    print(
        f"material-grub: {done} entry scenes + {len(keys)} class scenes baked; style {style}; rail: {' | '.join(' '.join(g) for g in groups)}"
    )
