"""Boot the safety nets in QEMU + OVMF. usage: python3 tests/fallback_smoke.py [WxH] [dark|light]
Needs: dist/material-grub, qemu-system-x86_64, OVMF, grub-mkimage, Pillow. Env: BOOT_WAIT (raise it without KVM).

Three boots of the same menu:
  themed      the normal result of the installer's rewrite (the baseline)
  no theme    theme.txt deleted after the install: the generated grub.cfg must skip `set theme` and show GRUB's plain menu
  rolled back the classes step is made to write a broken grub.cfg; the safety net must restore the old file byte for byte,
              and GRUB must boot that file into the themed menu
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "dist/material-grub"
res = sys.argv[1] if len(sys.argv) > 1 else "1920x1080"
scheme = sys.argv[2] if len(sys.argv) > 2 else "dark"
w, h = map(int, res.split("x"))
CFG = """set timeout=120
menuentry 'Fedora Linux (7.3.3-200.fc44.x86_64) 44 (Workstation Edition)' --class fedora --class gnu-linux --class os { true }
menuentry 'Arch Linux' --class arch --class gnu-linux --class gnu --class os { true }
menuentry 'Windows Boot Manager (on /dev/nvme0n1p1)' --class windows --class os { true }
menuentry 'UEFI Firmware Settings' --class efi { true }
"""
fail = []


def build(tree, break_classes=False):
    """A boot tree whose grub.cfg went through the real postprocess (static block + classes + scenes)."""
    shutil.rmtree(tree, ignore_errors=True)
    (tree / "boot/grub").mkdir(parents=True)
    cfg = tree / "boot/grub/grub.cfg"
    cfg.write_text(CFG)
    pkg = PKG
    if break_classes:  # a copy of the package whose classes tool writes a broken file
        pkg = tree.parent / (tree.name + "-pkg")
        shutil.rmtree(pkg, ignore_errors=True)
        shutil.copytree(PKG, pkg, symlinks=True, ignore=shutil.ignore_patterns("res", "scenes"))
        os.symlink(PKG / "res", pkg / "res")
        os.symlink(PKG / "scenes", pkg / "scenes")
        t = pkg / "bin/material-grub-classes"
        t.unlink()
        t.write_text("#!/usr/bin/env python3\nimport sys\nopen(sys.argv[1], 'a').write(\"menuentry 'broken' {\\n\")\n")
    state = tree / "state"
    env = dict(os.environ, MATERIAL_STATE_DIR=str(state), MATERIAL_CONF=str(tree / "material-grub.conf"))
    (tree / "material-grub.conf").write_text("STYLE=rail\n")
    cmd = [
        sys.executable,
        str(pkg / "bin/material-grub-postprocess"),
        "--pkg",
        str(pkg),
        "--immutable",
        "--cfg",
        str(cfg),
    ]
    cmd += [
        "--res",
        res,
        "--timeout",
        "120",
        "--backup",
        str(tree / "bk"),
        "--mirrors",
        str(tree / "boot/grub/material"),
    ]
    cmd += ["--mirrorbase", "/boot/grub/material", "--force"]
    return subprocess.run(cmd, env=env, capture_output=True, text=True), cfg


def shots(tree, name):
    subprocess.run(
        [sys.executable, ROOT / "scripts/qemu_tree.py", tree, res, "down"],
        check=True,
        env={**os.environ, "BOOT_WAIT": os.environ.get("BOOT_WAIT", "20"), "KEY_WAIT": os.environ.get("KEY_WAIT", "3")},
    )
    out = []
    for i in (0, 1):
        dst = ROOT / f"build/fallback-{scheme}-{name}-{i}.png"
        shutil.copy(ROOT / f"build/tree-{i}.png", dst)
        out.append(Image.open(dst).convert("RGB"))
    return out


def ink(im):
    """Fraction of bright pixels: a plain GRUB menu is white text on black."""
    g = im.convert("L").resize((w // 8, h // 8))
    return sum(1 for p in g.getdata() if p > 160) / (g.width * g.height)


def main():
    work = Path(tempfile.mkdtemp(prefix="material-grub-fallback."))
    try:
        # 1. themed baseline
        r, cfg = build(work / "themed")
        if r.returncode != 0:
            sys.exit("the baseline install failed:\n" + r.stderr)
        themed = shots(work / "themed", "themed")
        if max(ImageStat.Stat(themed[0].resize((96, 54))).stddev) < 12:
            fail.append("themed: image is nearly uniform (theme not drawn)")
        if ImageChops.difference(themed[0], themed[1]).getbbox() is None:
            fail.append("themed: the selection did not change the screen")

        # 2. theme missing at boot: plain menu, still usable
        r, cfg = build(work / "plain")
        theme_txt = work / "plain/boot/grub/themes/material/theme.txt"
        if "-f $prefix/themes/material/theme.txt" not in cfg.read_text():
            fail.append("the generated grub.cfg has no theme guard")
        theme_txt.unlink()
        plain = shots(work / "plain", "plain")
        if ImageChops.difference(plain[0], themed[0]).getbbox() is None:
            fail.append("plain: identical to the themed menu (theme.txt was deleted)")
        if ink(plain[0]) < 0.002:
            fail.append("plain: nothing is drawn (GRUB did not reach a menu)")
        if ImageChops.difference(plain[0], plain[1]).getbbox() is None:
            fail.append("plain: the menu does not react to the keyboard")
        if ink(plain[0]) > 0.2:
            fail.append("plain: too much ink for a plain GRUB menu (is the theme still loaded?)")

        # 3. a broken rewrite is rolled back and the old file boots
        before = CFG
        r, cfg = build(work / "rolled", break_classes=True)
        if r.returncode != 1:
            fail.append(f"rolled back: postprocess exited {r.returncode}, expected 1")
        if "rolled back" not in r.stderr:
            fail.append("rolled back: no rollback message on stderr")
        txt = cfg.read_text()
        if "broken" in txt or "classes applied" in txt:
            fail.append("rolled back: grub.cfg still holds the broken result")
        if "static theme begin" in txt:
            fail.append("rolled back: the static block of the failed run is still in grub.cfg")
        if txt != before:
            fail.append("rolled back: grub.cfg is not byte for byte the old file")
        # the old file has no theme at all (it is the file before our first run), so GRUB shows its plain menu with every entry
        rolled = shots(work / "rolled", "rolled")
        if ink(rolled[0]) < 0.002:
            fail.append("rolled back: GRUB shows nothing from the restored grub.cfg")
        if ImageChops.difference(rolled[0], rolled[1]).getbbox() is None:
            fail.append("rolled back: the restored menu does not react to the keyboard")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if fail:
        sys.exit("FALLBACK SMOKE TEST FAILED:\n  " + "\n  ".join(fail))
    print(f"fallback smoke test ok ({res}, {scheme}): shots in build/fallback-*.png")


main()
