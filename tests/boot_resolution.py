"""Boot the built package in QEMU + OVMF on an awkward screen (1360x768: no built-in size, and a size most laptops report as 1366x768) and check that GRUB fills it.
usage: python3 tests/boot_resolution.py   Needs: dist/material-grub, qemu-system-x86_64, OVMF, grub-mkimage, Pillow. Env: BOOT_WAIT (raise it without KVM).
The image is built with MG_QEMU_GOP_ONLY=1: only the firmware's own GOP modes, like a real UEFI machine (QEMU's Bochs driver would accept any mode and hide the bug).
Cases: the theme written for exactly the screen (`1360x768`), the theme asked for 1366x768 on a screen that only has 1360x768 (centred, not in a corner), and the basic theme."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "dist/material-grub"
BIN = PKG / "bin"
SCREEN = "1360x768"
CFG = """set timeout=120
set gfxmode={gfx}
set gfxpayload=keep
insmod all_video
insmod gfxterm
insmod gfxmenu
insmod png
terminal_output gfxterm
loadfont /boot/grub/themes/material/MG-Label.pf2
loadfont /boot/grub/themes/material/MG-Raw.pf2
set theme=/boot/grub/themes/material/theme.txt
menuentry 'Fedora Linux (6.12.1) 44 (Workstation Edition)' --class fedora --class gnu-linux --class gnu --class os {{ true }}
menuentry 'Arch Linux' --class arch --class gnu-linux --class gnu --class os {{ true }}
menuentry 'Restart' --class restart --id material-reboot {{ reboot }}
"""


def shot(name, mode, gfx):
    tree = ROOT / f"build/res-{name}"
    shutil.rmtree(tree, ignore_errors=True)
    (tree / "boot/grub").mkdir(parents=True)
    (tree / "boot/grub/grub.cfg").write_text(CFG.format(gfx=gfx))
    th, state = tree / "boot/grub/themes/material", tree / "state/entries.json"
    run = lambda *a: subprocess.run([sys.executable, *map(str, a)], check=True, stdout=subprocess.DEVNULL)  # noqa: E731
    run(BIN / "material-grub-assemble", "--mode", mode, "--pkg", PKG, "--out", th)
    run(BIN / "material-grub-classes", tree / "boot/grub/grub.cfg", "--pkg", PKG, "--state", state)
    run(BIN / "material-grub-scenes", "--theme", th, "--state", state, "--pkg", PKG)
    env = {**os.environ, "MG_QEMU_GOP_ONLY": "1", "BOOT_WAIT": os.environ.get("BOOT_WAIT", "40"), "KEY_WAIT": "3"}
    subprocess.run([sys.executable, ROOT / "scripts/qemu_tree.py", tree, SCREEN], check=True, env=env)
    out = ROOT / f"build/res-{name}.png"
    shutil.copy(ROOT / "build/tree-0.png", out)
    return Image.open(out).convert("RGB")


def check(name, mode, gfx):
    im = shot(name, mode, gfx)
    w, h = im.size
    assert (w, h) == tuple(map(int, SCREEN.split("x"))), f"{name}: the screen is {w}x{h}"
    corners = {im.getpixel(p) for p in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3))}
    assert len(corners) == 1, f"{name}: the corners differ {corners} (a gray edge, or a theme in one corner)"
    r, g, b = corners.pop()
    assert (r, g, b) != (0, 0, 0) and not (abs(r - g) < 3 and abs(g - b) < 3 and r > 60), (
        f"{name}: a black or gray corner {(r, g, b)}"
    )
    # the menu is drawn: the selected row is a bright pill, far from the background colour
    bright = sum(1 for p in im.getdata() if sum(p) > 600)
    assert bright > 2000, f"{name}: no menu is drawn ({bright} bright pixels)"
    print(f"ok {name}: {w}x{h}, corner {(r, g, b)}")


if __name__ == "__main__":
    check("exact", "1360x768", "1360x768,auto")
    check("near-miss", "1366x768", "1360x768")  # asked for 1366x768, the firmware only has 1360x768
    check("basic", "basic", "auto")
