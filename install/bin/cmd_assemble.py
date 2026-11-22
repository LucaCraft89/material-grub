"""Assemble the active theme directory for a given gfx mode. stdlib only.
usage: material-grub-assemble --mode WxH --pkg DIR --out DIR   (prints the mode the theme was written for, or `auto` for the basic theme)"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import mgrub
import mgsafe
import mgtheme


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


def bundle_sizes(text):
    """(label font size, raw font size) named in a built bundle's theme.txt: the fonts and pictures that are copied carry those sizes in their names."""
    fs, rs = re.search(r"MG-Label Regular (\d+)", text), re.search(r"MG-Raw Regular (\d+)", text)
    return int(fs[1]) if fs else 26, int(rs[1]) if rs else 20


def main():
    pkg, out = Path(arg("--pkg", "/usr/share/material-grub")), Path(arg("--out"))
    mode_arg = (arg("--mode", "") or "").strip()
    avail = sorted(p.name for p in (pkg / "res").iterdir())
    req = mgtheme.first_mode(mode_arg)
    basic = False
    if req is None:
        if mode_arg.split(",")[0].strip() in ("", "auto"):
            req = (1920, 1080)  # 'auto' / unset: the size this theme has always assumed
        else:
            basic = True  # `basic` asked for, or a mode nobody can use ('keep', 'banana', 99999x5): no pixel-exact theme can be right, so the plain one that fits any screen
            if mode_arg.split(",")[0].strip() != "basic":
                print(
                    f"material-grub: '{mode_arg}' is not a usable screen mode: using the basic theme that fits any screen",
                    file=sys.stderr,
                )
            req = (1920, 1080)
    w, h = req
    exact = f"{w}x{h}" in avail
    asset = (
        f"{w}x{h}" if exact else mgrub.snap(f"{w}x{h}", avail)
    )  # the bundle whose fonts, bar pictures and scene set are used
    if not exact and not basic:
        print(
            f"material-grub: {w}x{h} is not a built-in size: the theme is written for exactly {w}x{h} (scenes and fonts of the {asset} bundle)",
            file=sys.stderr,
        )
    res = pkg / "res" / asset
    aspect = (res / "aspect").read_text().strip()
    light = (pkg / "scheme.txt").exists() and (pkg / "scheme.txt").read_text().strip() == "light"
    tmp = out.with_name(out.name + ".new")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for f in res.iterdir():
        if f.name not in ("logo_size", "aspect", "theme.txt"):
            shutil.copy(f, tmp / f.name)
    conf = mgrub.load_conf()
    bundle_text = (res / "theme.txt").read_text()
    fs, rs = bundle_sizes(bundle_text)
    bar_h = max(8, round(14 * int(asset.split("x")[1]) / 1080))
    if exact:
        text = bundle_text
    else:
        text = mgtheme.theme_text(
            w, h, wds=mgtheme.ASPECTS[aspect.split("@")[0]], light=light, aspect=aspect, fs=fs, rs=rs, bh=bar_h
        )
    th = tmp / "theme.txt"
    # /etc/material-grub.conf: raw name / countdown / logo on or off (and the style's layout), then every position relative to the screen's centre
    sized = mgtheme.anchor_centre(mgrub.apply_conf_to_theme(text, conf), w, h)
    th.write_text(sized)
    basic_text = mgrub.apply_conf_to_theme(mgtheme.basic_theme_text(light, fs, rs, bar_h), dict(conf, STYLE="rail"))
    (tmp / "theme-basic.txt").write_text(
        basic_text
    )  # always shipped: `theme=.../theme-basic.txt` is the way out of any size trouble
    if basic:
        th.write_text(basic_text)
    (tmp / ".mode").write_text("auto" if basic else f"{w}x{h}")
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
    logo_px = round(120 * h / 1080)  # the firmware logo in the top-right cookie, sized for this screen
    if conf["LOGO"] == "on" and conf["COOKIE"] == "on" and not basic:
        subprocess.run(
            [
                sys.executable,
                str(pkg / "bin/bgrt-logo.py"),
                str(tmp / "machine-logo.png"),
                "--size",
                str(logo_px),
            ],
            check=False,
            stdout=subprocess.DEVNULL,
        )
        penguin_if_no_logo(tmp / "machine-logo.png", pkg, logo_px)
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
    print("auto" if basic else f"{w}x{h}")
