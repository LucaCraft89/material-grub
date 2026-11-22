"""Immutable / static grub.cfg mode (ostree, bootc). stdlib only. Idempotent.

On these systems grub2-mkconfig is never run: /boot/grub2/grub.cfg is a static file written at install time (and by `bootupctl update`),
so the /etc/grub.d hooks never execute. This does what 05_material, 15_material_menu and 90_material_system do, directly on that file:
  - assembles the theme directory next to grub.cfg (<grubdir>/themes/material)
  - inserts a managed block that loads the theme, keeps the menu visible (before the first `blscfg`)
  - appends the Restart / Shut down entries (end of file)
  - keeps an untouched copy of the file as it was before we first modified it (for --restore / uninstall)
usage: material-grub-static GRUB_CFG --mode WxH [--pkg DIR] [--backup DIR] [--timeout N]
       material-grub-static GRUB_CFG --restore [--backup DIR]"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import grubscript
import mgrub


def arg(n, d=None):
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d


A, B = "# material-grub: static theme begin", "# material-grub: static theme end"
C, D = "# material-grub: system entries begin", "# material-grub: system entries end"
MARK = "# material-grub: classes applied"  # written by material-grub-classes


def strip(text, pairs):
    for a, b in pairs:
        text = re.sub(rf"(?ms)^{re.escape(a)}\n.*?^{re.escape(b)}\n", "", text)
    return text


system = f"""{C}
menuentry 'Restart' --class restart --id material-reboot {{ reboot }}
menuentry 'Shut down' --class shutdown --id material-halt {{ halt }}
{D}
"""


def insertion_line(body, lines):
    """Index of the line the theme block goes before: the first `blscfg` call (or our structured-BLS block), else the first menu entry.
    Found with the GRUB script scanner, so a line inside a quoted title or a comment is never taken for a command."""
    sc = grubscript.scan(body)
    first_entry = None
    for i, ln in enumerate(lines):
        cmd = sc.command_at_line(i)
        if cmd is not None and cmd.value == "blscfg" and mgrub.bls_call(ln.rstrip("\n")) is not None:
            return i
        com = sc.comment_at_line(i)
        if com is not None and com.text.startswith("# material-grub: structured BLS"):
            return i
        if first_entry is None and cmd is not None and cmd.value in ("menuentry", "submenu"):
            first_entry = i
    return len(lines) if first_entry is None else first_entry


def main():
    cfg = Path(sys.argv[1]).resolve()  # resolve: /boot/grub2/grub.cfg may be a symlink
    pkg = Path(arg("--pkg", "/usr/share/material-grub"))
    backup = Path(arg("--backup", "/var/backups/material-grub"))
    pristine = backup / "grub.cfg.pre-material"
    if "--restore" in sys.argv:
        if not pristine.exists():
            sys.exit(f"material-grub-static: no pristine copy in {backup}")
        shutil.copy2(pristine, cfg)
        print(f"material-grub-static: restored {cfg}")
        sys.exit(0)
    mode = arg("--mode")
    timeout = mgrub.load_conf()["TIMEOUT"] or arg("--timeout", "5")  # TIMEOUT in /etc/material-grub.conf wins
    if not mode:
        sys.exit("material-grub-static: --mode WxH required")
    text = cfg.read_text()
    if (
        MARK not in text and A not in text
    ):  # a file we have never touched (first run, or bootupd just rewrote it): remember it
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cfg, pristine)
    grubdir = cfg.parent
    theme = grubdir / "themes/material"
    out = subprocess.run(
        [
            sys.executable,
            str(pkg / "bin/material-grub-assemble"),
            "--mode",
            mode,
            "--pkg",
            str(pkg),
            "--out",
            str(theme),
        ],
        capture_output=True,
        text=True,
    )
    chosen = out.stdout.strip().splitlines()[-1] if out.stdout.strip() else ""
    if out.returncode or not chosen:
        sys.exit("material-grub-static: theme assembly failed: " + out.stderr.strip())
    UNI = (
        "loadfont $prefix/themes/material/unicode.pf2\n" if (theme / "unicode.pf2").exists() else ""
    )  # non-Latin fallback glyphs
    gfx = "auto" if chosen == "auto" else f"{chosen},auto"  # `auto`: the basic theme that fits any screen
    block = f"""{A}
set gfxmode={gfx}
set gfxpayload=keep
insmod all_video
insmod gfxterm
insmod gfxmenu
insmod png
terminal_output gfxterm
if [ -f $prefix/themes/material/theme.txt -a -d $prefix/themes/material/icons ]; then
loadfont $prefix/themes/material/MG-Label.pf2
loadfont $prefix/themes/material/MG-Raw.pf2
{UNI}set theme=$prefix/themes/material/theme.txt
export theme
fi
set timeout_style=menu
set timeout={timeout}
unset menu_hide_ok
{B}
"""
    had_system = C in text
    body = strip(text, [(A, B)] + ([] if had_system else [(C, D)]))
    lines = grubscript.split_lines(body)
    at = insertion_line(body, lines)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    new = "".join(lines[:at]) + block + "".join(lines[at:]) + ("" if had_system else system)
    if new != text:
        tmp = cfg.with_name(cfg.name + ".material-tmp")
        tmp.write_text(new)
        os.chmod(tmp, cfg.stat().st_mode)
        os.replace(tmp, cfg)
        print(f"material-grub-static: updated {cfg} (theme {chosen})")
    else:
        print("material-grub-static: nothing to do")
