"""Boot what the unified installer installed (tests/containers/installed_tree.sh wrote the tree) in QEMU + OVMF and check what GRUB really draws: the screen is
the size the installer was asked for, the theme is drawn (not the plain menu), the picture follows the selection, and the dark scheme is dark.
usage: python3 tests/boot_installed.py TREE [WxH]. Needs qemu-system-x86_64, OVMF, grub-mkimage, Pillow. Env: BOOT_WAIT (raise it without KVM)."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parent.parent
tree = Path(sys.argv[1]).resolve()
res = sys.argv[2] if len(sys.argv) > 2 else "1920x1080"
w, h = map(int, res.split("x"))
subprocess.run(
    [sys.executable, ROOT / "scripts/qemu_tree.py", tree, res, "down", "down"],
    check=True,
    env={**os.environ, "BOOT_WAIT": os.environ.get("BOOT_WAIT", "60"), "KEY_WAIT": os.environ.get("KEY_WAIT", "4")},
)
out = ROOT / "build/installed-shots"
out.mkdir(parents=True, exist_ok=True)
shots = []
for i in range(3):
    shutil.copy(ROOT / f"build/tree-{i}.png", out / f"installed-{i}.png")
    shots.append(Image.open(out / f"installed-{i}.png").convert("RGB"))
fail = []
for i, im in enumerate(shots):
    if im.size != (w, h):
        fail.append(
            f"shot {i}: the screen is {im.size}, expected {(w, h)} (GRUB did not set the mode, or fell back to the basic theme)"
        )
    colours = im.getcolors(maxcolors=im.size[0] * im.size[1]) or []
    if len(colours) < 50 or max(colours)[1] == (0, 0, 0):
        fail.append(
            f"shot {i}: {len(colours)} colours, the commonest {max(colours)[1] if colours else None}: that is the plain black menu, not the Material theme"
        )
    if max(ImageStat.Stat(im.resize((96, 54))).stddev) < 12:
        fail.append(f"shot {i}: the picture is nearly uniform (the theme is not drawn)")
    if sum(ImageStat.Stat(im.resize((32, 18))).mean) / 3 >= 128:
        fail.append(f"shot {i}: not dark: the installer was asked for the dark scheme")
for a, b in ((0, 1), (1, 2)):
    if ImageChops.difference(shots[a], shots[b]).getbbox() is None:
        fail.append(f"shots {a} and {b} are identical: the selection did not change the scene")
if fail:
    sys.exit("BOOT OF THE INSTALLED RESULT FAILED:\n  " + "\n  ".join(fail))
print(f"the installed result boots themed at {res}: shots in {out}")
