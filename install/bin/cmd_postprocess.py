"""Re-apply Material GRUB: annotate grub.cfg, refresh the BLS mirrors, bake the per-entry scenes. stdlib only.
Every rewrite of grub.cfg goes through mgsafe.guarded: the result is validated, and the previous file is restored if it is not valid.
usage: material-grub-postprocess [--pkg DIR] [--immutable --res WxH --timeout N] [--cfg FILE [--theme DIR]] [--force]
  --cfg/--theme  work on this grub.cfg and theme directory instead of the system ones (tests, doctor)
  --force     retry a grub.cfg that already failed validation (its sha256 is in /var/lib/material-grub/last-error)
Exit status: 0 applied or nothing to do, 1 rolled back (the menu is as before; see the box on stderr)."""

import os
import subprocess
import sys
from pathlib import Path

import mgsafe


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def tool(pkg, name, *args):
    cmd = [sys.executable, str(Path(pkg) / "bin" / name), *map(str, args)]
    return subprocess.run(cmd).returncode == 0


def apply_normal(cfg, pkg, theme, force):
    def classes():
        return tool(pkg, "material-grub-classes", cfg, "--pkg", pkg)

    def scenes():
        # the scene renderer needs Pillow; without it the tool exits 0 and the theme keeps its class scenes
        return (
            tool(pkg, "material-grub-scenes", "--theme", theme, "--pkg", pkg)
            if theme and Path(theme).is_dir()
            else True
        )

    return mgsafe.guarded(
        cfg, [classes, scenes], theme=theme if theme and Path(theme).is_dir() else None, pkg=pkg, force=force
    )


def apply_immutable(cfg, pkg, res, timeout, force):
    real = Path(cfg).resolve()
    gdir = real.parent
    boot_mount = os.path.ismount("/boot")
    mbase = (str(gdir)[len("/boot") :] if boot_mount else str(gdir)) + "/material"
    theme = gdir / "themes/material"

    def static():
        return tool(pkg, "material-grub-static", cfg, "--mode", res, "--pkg", pkg, "--timeout", timeout)

    def classes():
        return tool(
            pkg,
            "material-grub-classes",
            cfg,
            "--pkg",
            pkg,
            "--mirrors",
            gdir / "material",
            "--mirrorbase",
            mbase,
            "--fallback-all",
        )

    def scenes():
        return tool(pkg, "material-grub-scenes", "--theme", theme, "--pkg", pkg) if theme.is_dir() else True

    return mgsafe.guarded(
        real, [static, classes, scenes], theme=theme if theme.is_dir() else None, pkg=pkg, force=force
    )


def main():
    pkg = arg("--pkg", os.environ.get("MATERIAL_PKG", "/usr/share/material-grub"))
    force = "--force" in sys.argv or os.environ.get("MG_FORCE") == "1"
    results = []
    if "--immutable" in sys.argv:
        for f in ("/boot/grub2/grub.cfg", "/boot/grub/grub.cfg"):
            if Path(f).is_file():
                results.append(apply_immutable(f, pkg, arg("--res", "1920x1080"), arg("--timeout", "5"), force))
    elif arg("--cfg"):
        results.append(apply_normal(arg("--cfg"), pkg, arg("--theme"), force))
    else:
        for f, t in (
            ("/boot/grub2/grub.cfg", "/boot/grub2/themes/material"),
            ("/boot/grub/grub.cfg", "/boot/grub/themes/material"),
        ):
            if Path(f).is_file():
                results.append(apply_normal(f, pkg, t, force))
    return 1 if "rolled-back" in results else 0
