"""Assemble the active theme directory for a given gfx mode. stdlib only.
usage: material-grub-assemble --mode WxH --pkg DIR --out DIR   (prints the resolution actually chosen)"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import mgrub
import mgsafe


def arg(n, d=None):
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d


def penguin_if_no_logo(path, pkg, size):
    """bgrt-logo.py writes a 1x1 transparent PNG when the firmware has no logo (a VM, many desktops): draw the Linux penguin instead. Needs Pillow; without it the cookie stays empty."""
    try:
        import mgscenes
        from PIL import Image

        if Image.open(path).size != (1, 1):
            return
        im = mgscenes.tux_logo(pkg, size)
        if im is not None:
            im.save(path)
    except (ImportError, OSError):
        pass


def main():
    pkg, out = Path(arg("--pkg", "/usr/share/material-grub")), Path(arg("--out"))
    mode = (arg("--mode", "") or "").split(",")[0].split("x")
    avail = sorted(p.name for p in (pkg / "res").iterdir())

    try:
        w, h = int(mode[0]), int(mode[1])
    except Exception:
        w, h = 1920, 1080  # 'auto'/unset -> safe default
    if f"{w}x{h}" in avail:
        best = f"{w}x{h}"
    else:  # nearest by aspect ratio first, then by size
        best = mgrub.snap(f"{w}x{h}", avail)
        print(f"material-grub: {w}x{h} unsupported, using {best}", file=sys.stderr)
    res = pkg / "res" / best
    aspect = (res / "aspect").read_text().strip()
    tmp = out.with_name(out.name + ".new")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for f in res.iterdir():
        if f.name not in ("logo_size", "aspect"):
            shutil.copy(f, tmp / f.name)
    conf = mgrub.load_conf()
    th = tmp / "theme.txt"
    th.write_text(
        mgrub.apply_conf_to_theme(th.read_text(), conf)
    )  # /etc/material-grub.conf: raw name / countdown / logo on or off
    (tmp / "icons").mkdir()
    [shutil.copy(pkg / "fonts" / n, tmp / n) for n in ("OFL.txt", "TRADEMARKS.md") if (pkg / "fonts" / n).exists()]
    (tmp / ".aspect").write_text(aspect)
    for cand in (
        "/usr/share/grub/unicode.pf2",
        "/usr/share/grub2/unicode.pf2",
        "/usr/share/fonts/grub/unicode.pf2",
        "/usr/share/fonts/truetype/unifont/unicode.pf2",
        "/boot/grub/fonts/unicode.pf2",
        "/boot/grub2/fonts/unicode.pf2",
    ):
        if os.path.exists(cand):
            shutil.copy(cand, tmp / "unicode.pf2")
            break
    classes = json.loads((pkg / "classes.json").read_text())
    for _key, names in classes.items():
        src = pkg / "scenes" / aspect / "icons" / f"{names[0]}.png"
        for n in names:
            shutil.copyfile(src, tmp / "icons" / f"{n}.png")
    if conf["LOGO"] == "on" and conf["COOKIE"] == "on":
        subprocess.run(
            [
                sys.executable,
                str(pkg / "bin/bgrt-logo.py"),
                str(tmp / "machine-logo.png"),
                "--size",
                (res / "logo_size").read_text().strip(),
            ],
            check=False,
            stdout=subprocess.DEVNULL,
        )
        penguin_if_no_logo(tmp / "machine-logo.png", pkg, int((res / "logo_size").read_text().strip()))
    problems = mgsafe.theme_problems(tmp, pkg)
    if problems:  # keep the theme that is installed now; the half-built one is dropped
        shutil.rmtree(tmp, ignore_errors=True)
        sys.exit("material-grub-assemble: the new theme is incomplete, keeping the old one: " + "; ".join(problems))
    old = out.with_name(out.name + ".old")  # swap with the old directory kept until the new one is in place
    shutil.rmtree(old, ignore_errors=True)
    if out.exists():
        os.rename(out, old)
    try:
        os.replace(tmp, out)
    except OSError:
        if old.exists():
            os.rename(old, out)
        raise
    shutil.rmtree(old, ignore_errors=True)
    print(best)
