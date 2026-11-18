"""Where the GUI finds the installed theme package and the shared modules (mgrub, mgoverrides, mgscenes, ...). stdlib only.

Installed:  /usr/share/material-grub (the theme package, with its bin/ of shared modules); $MATERIAL_PKG moves it.
A checkout: the repository's install/bin for the modules and dist/material-grub (a built package) for scenes, glyphs and fonts.
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent  # only meaningful in a checkout


def in_checkout():
    return (REPO / "install/bin/mgrub.py").is_file()


def package():
    """The theme package directory: has palettes.json, glyphs/, scenes/. From a checkout, a built dist/ package wins over the installed one."""
    dist = str(REPO / "dist/material-grub")
    cands = [os.environ.get("MATERIAL_PKG"), dist, "/usr/share/material-grub", "/var/lib/material-grub/pkg"]
    if not in_checkout():
        cands = [os.environ.get("MATERIAL_PKG"), "/usr/share/material-grub", "/var/lib/material-grub/pkg"]
    for c in cands:
        if c and (Path(c) / "palettes.json").is_file():
            return Path(c)
    return None


def modules_dir(pkg=None):
    """The directory with mgrub.py and friends: <pkg>/bin when installed, install/bin in a checkout."""
    order = [REPO / "install/bin", (Path(pkg) / "bin") if pkg else None] if in_checkout() else [(Path(pkg) / "bin") if pkg else None]
    for c in order:
        if c and (c / "mgrub.py").is_file():
            return c
    return None


def setup():
    """Put the shared modules on sys.path. Returns (package dir or None, modules dir)."""
    pkg = package()
    mods = modules_dir(pkg)
    if mods is None:
        raise SystemExit("material-grub is not installed (no shared modules found); install it first")
    for p in (str(mods), str(HERE)):
        if p not in sys.path:
            sys.path.insert(0, p)
    return pkg, mods
