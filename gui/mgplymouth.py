"""The GUI's view of the optional Plymouth part: a still picture of what the boot splash will show, drawn from the GUI's unsaved draft. stdlib only.

It does not draw anything itself. It writes the draft (conf, overrides, the uploaded icons, this machine's os-release) into a scratch root and runs
`material-grub plymouth preview SCREEN FILE --root SCRATCH` (the plugin's own command), so the picture is made by the same code that will write the real
theme. A unprivileged user can run it: nothing outside the scratch directory is touched.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCREENS = ("boot", "password", "shutdown")
SIZE_MIN, SIZE_MAX = (320, 180), (3840, 2160)


def parse_size(text):
    """'1280x720' -> (1280, 720), or raises ValueError. Bounded: a preview is a picture, not a way to make the machine draw a gigapixel."""
    try:
        w, h = (int(v) for v in str(text).lower().split("x"))
    except ValueError:
        raise ValueError("the size must look like 1280x720") from None
    if not (SIZE_MIN[0] <= w <= SIZE_MAX[0] and SIZE_MIN[1] <= h <= SIZE_MAX[1]):
        raise ValueError("the size is outside 320x180 to 3840x2160")
    return w, h


def os_release():
    for f in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            return Path(f).read_text()
        except OSError:
            continue
    return ""


def still(mods, draft, screen, size, icon_dirs=(), timeout=90):
    """PNG bytes of `screen` for the draft `{conf, overrides}` (already validated). Raises RuntimeError with a readable message when the part cannot draw it."""
    if screen not in SCREENS:
        raise ValueError("unknown screen " + str(screen))
    w, h = parse_size(size)
    cli = Path(mods) / "cmd_cli.py"
    if not cli.is_file():
        raise RuntimeError("material-grub's command line is not installed next to the GUI")
    with tempfile.TemporaryDirectory(prefix="mg-gui-plymouth-") as td:
        root = Path(td) / "root"
        (root / "etc/material-grub").mkdir(parents=True)
        # the conf the part reads: the defaults of the keys the draft does not set are the part's own (load_conf fills them in)
        (root / "etc/material-grub.conf").write_text("".join(f"{k}={v}\n" for k, v in draft["conf"].items()))
        (root / "etc/material-grub/overrides.json").write_text(json.dumps(draft["overrides"]))
        (root / "etc/os-release").write_text(os_release())
        icons = root / "etc/material-grub/icons"
        icons.mkdir()
        for d in icon_dirs:  # the installed pictures first, then the ones uploaded in this session (they win)
            try:
                for f in Path(d).iterdir():
                    if f.is_file():
                        shutil.copy(f, icons / f.name)
            except OSError:
                continue
        out = Path(td) / "still.png"
        cmd = [
            sys.executable,
            str(cli),
            "plymouth",
            "preview",
            screen,
            str(out),
            "--size",
            f"{w}x{h}",
            "--root",
            str(root),
        ]
        env = {
            **os.environ,
            "MATERIAL_OVERRIDES": str(root / "etc/material-grub/overrides.json"),
            "MATERIAL_CONF": str(root / "etc/material-grub.conf"),
        }
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                stdin=subprocess.DEVNULL,
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("the Plymouth preview took too long") from None
        if r.returncode != 0 or not out.is_file():
            tail = " ".join((r.stdout + r.stderr).split())[-300:]
            raise RuntimeError(
                "the Plymouth part could not draw the preview: " + (tail or f"exit status {r.returncode}")
            )
        return out.read_bytes()
