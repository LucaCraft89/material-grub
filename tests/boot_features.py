"""Boot a themed tree in QEMU + OVMF with the new customisations and check what GRUB really draws: one seed colour, a custom entry colour and name,
Windows first, hidden entries, and the firmware logo (the penguin on a machine without one) in the cookie.
usage: python3 tests/boot_features.py SCENARIO [STYLE] [WxH]     SCENARIO: single | entry | order | hidden | logo
Needs: dist/material-grub, qemu-system-x86_64, OVMF, grub-mkimage, Pillow. Env: BOOT_WAIT / KEY_WAIT (raise them without KVM). Screenshots: build/feature-shots/."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "install/bin"))
import make_screenshots as M  # noqa: E402
import mgpalette  # noqa: E402

PKG = ROOT / "dist/material-grub"
scenario = sys.argv[1] if len(sys.argv) > 1 else "single"
style = sys.argv[2] if len(sys.argv) > 2 else "rail"
res = sys.argv[3] if len(sys.argv) > 3 else "1920x1080"
w, h = map(int, res.split("x"))
dark = (PKG / "scheme.txt").read_text().strip() != "light"
base_pal = json.loads((PKG / "palettes.json").read_text())

SCENARIOS = {
    "single": {"seed": {"mode": "single", "color": "#7E57C2"}},
    "entry": {"entries": [{"match": {"key": "fedora"}, "color": "#E95420", "name": "Work laptop"}]},
    "order": {"groups": ["windows", "linux", "system"]},
    "hidden": {
        "entries": [{"match": {"title": "windows"}, "hidden": True}, {"match": {"title": "ubuntu"}, "hidden": True}]
    },
    "logo": {},
}
if scenario not in SCENARIOS:
    sys.exit(f"unknown scenario {scenario}: " + ", ".join(SCENARIOS))
work = ROOT / f"build/feature-{scenario}-{style}"
shutil.rmtree(work, ignore_errors=True)
work.mkdir(parents=True)
(work / "mg.conf").write_text(f"STYLE={style}\n")
(work / "overrides.json").write_text(json.dumps({"version": 1, **SCENARIOS[scenario]}))
os.environ["MATERIAL_CONF"] = str(work / "mg.conf")  # never the real /etc
os.environ["MATERIAL_OVERRIDES"] = str(work / "overrides.json")
os.environ.setdefault("MG_BGRT_IMAGE", "/nonexistent/bgrt")  # a machine without a firmware logo: the penguin
tree = ROOT / "build/ci-tree"
M.build_tree(res, tree)
cfg = (tree / "boot/grub/grub.cfg").read_text()
keys = ["down", "down"]
subprocess.run(
    [sys.executable, ROOT / "scripts/qemu_tree.py", tree, res, *keys],
    check=True,
    env={**os.environ, "BOOT_WAIT": os.environ.get("BOOT_WAIT", "20"), "KEY_WAIT": os.environ.get("KEY_WAIT", "3")},
)
out = ROOT / "build/feature-shots"
out.mkdir(exist_ok=True)
names = ["first", "second", "third"]
shots = []
for i, n in enumerate(names):
    dst = out / f"{scenario}-{style}-{n}.png"
    shutil.copy(ROOT / f"build/tree-{i}.png", dst)
    shots.append(Image.open(dst).convert("RGB"))


def rgb(hexcolor):
    return tuple(int(hexcolor[i : i + 2], 16) for i in (1, 3, 5))


def surface(im):
    """The scene's own background colour: a corner outside the cookie; in `clean` the panel sits inside a margin that has the neutral base colour, so look inside the panel."""
    return im.getpixel((200, 130)) if style == "clean" else im.getpixel((w - 3, 3))


fail = []
for im, n in zip(shots, names):
    if im.size != (w, h):
        fail.append(f"{n}: screen is {im.size}, expected {(w, h)}")
    if max(ImageStat.Stat(im.resize((96, 54))).stddev) < 12:
        fail.append(f"{n}: image is nearly uniform (theme not drawn)")
if scenario == "single":
    want = rgb(mgpalette.scheme("#7E57C2", dark)["surface"])
    for im, n in zip(shots, names):
        if surface(im) != want:
            fail.append(f"{n}: background {surface(im)} is not the single seed's surface {want}")
elif scenario == "entry":
    want = rgb(mgpalette.scheme("#E95420", dark)["surface"])
    if surface(shots[0]) != want:
        fail.append(f"the Fedora entry should use the custom colour {want}, got {surface(shots[0])}")
    if surface(shots[2]) == want:
        fail.append("the custom colour leaked onto other entries")
    if "Work laptop" in cfg:
        fail.append("the new name must not be written into grub.cfg (GRUB titles stay as they are)")
elif scenario == "order":
    win = rgb(base_pal["windows11"]["surface"])
    fed = rgb(base_pal["fedora"]["surface"])
    if surface(shots[0]) != win:
        fail.append(f"Windows should come first: first screen {surface(shots[0])}, Windows is {win}")
    if surface(shots[1]) != fed:
        fail.append(f"Fedora should be second: second screen {surface(shots[1])}, Fedora is {fed}")
    if cfg.find("Windows Boot Manager") > cfg.find("blscfg") and "material-grub: structured BLS" in cfg:
        pass  # the Windows block moved above the BLS block, checked through the screens
elif scenario == "hidden":
    for gone in ("Windows Boot Manager", "Ubuntu 24.04"):
        if f"menuentry '{gone}" in cfg:
            fail.append(f"{gone} is still a menuentry in grub.cfg")
    if "hidden by overrides.json" not in cfg:
        fail.append("grub.cfg has no 'hidden by overrides.json' marker")
elif scenario == "logo":
    logo = Image.open(tree / "boot/grub/themes/material/machine-logo.png")
    if logo.size == (1, 1):
        fail.append("machine-logo.png is the empty 1x1 image: the penguin fallback did not run")
    cx, cy = (w - 150, 140) if style != "clean" else (w - 24 - 150, 96 + 140)
    box = shots[0].crop((cx - 60, cy - 60, cx + 60, cy + 60)).convert("L")
    dark_px = sum(1 for v in box.getdata() if v < 60)
    if dark_px < 150:
        fail.append(f"no firmware logo (penguin) drawn in the cookie: {dark_px} dark pixels in its box")
if fail:
    sys.exit(f"BOOT FEATURES TEST FAILED ({scenario}, {style}):\n  " + "\n  ".join(fail))
print(f"boot features ok ({scenario}, {style}, {res}): shots in {out}")
