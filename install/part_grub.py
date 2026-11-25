"""material-grub as a part of Material Boot (API 2): the entry file of material-boot-part.json.

The hooks are thin. The work is done by install/installer.py (the same program `sudo ./install.sh` runs), started as a child process with the options the unified
installer collected, so that both entry points do the same thing and the tests of one are tests of the other. docs/plans/g2-grub-part.md has the design.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # the repository, or parts/grub in a bundle
sys.path.insert(0, str(HERE / "install/bin"))
import material_boot  # noqa: E402  (the core that is running this: the tools must use the same one)

os.environ.setdefault("MATERIAL_LIB", str(Path(material_boot.__file__).resolve().parent.parent))
import mgcore  # noqa: E402,F401
import mgdetect  # noqa: E402
from material_boot.conf import (
    CONF_DEFAULTS as DEFAULTS,  # noqa: E402  (the conf the core loads has the defaults filled in)
)

FLAGS = {
    "stage-only": "--stage-only",
    "immutable": "--immutable",
    "with-gui": "--with-gui",
    "no-deps": "--no-deps",
    "keep-build": "--keep-build",
}
VALUES = {"res": "--res", "mode": "--mode", "ventoy": "--ventoy", "pkg": "--pkg", "dist-out": "--dist-out"}
LOOK = {"STYLE": "--style", "SCHEME": "--scheme"}
SWITCH = {"COOKIE": ("--cookie", "--no-cookie"), "LOGO": ("--logo", "--no-logo"), "HINTS": ("--hints", "--no-hints")}


def engine_args(ctx, *extra):
    """The command line of install/installer.py for what the unified installer was asked: its own options, and the shared look the core already wrote (the
    engine would otherwise ask or fall back to its defaults). It never asks: the core did, before any part ran."""
    a = ["--yes", "--no-tui"]
    o = ctx.options
    for name, flag in FLAGS.items():
        if o.get(name):
            a.append(flag)
    for name, flag in VALUES.items():
        if o.get(name) not in (None, False):
            a += [flag, str(o[name])]
    # Only what differs from the default is passed: install.sh writes what was chosen and leaves the rest as commented samples, and the files must be the same.
    for key, flag in LOOK.items():
        if ctx.conf.get(key) and ctx.conf[key] != DEFAULTS.get(key):
            a += [flag, str(ctx.conf[key])]
    for key, (on, off) in SWITCH.items():
        v = ctx.conf.get(key)
        if v in ("on", "off") and v != DEFAULTS.get(
            key
        ):  # a default is left as it is: install.sh writes only what was chosen, and the files must be the same
            a.append(on if v == "on" else off)
    if ctx.how == "package":
        a.append("--from-package")
    elif ctx.how == "immutable" and "--immutable" not in a:
        a.append("--immutable")
    if ctx.json:
        a += ["--progress", "json"]
    return a + list(extra)


def run_engine(ctx, args):
    """Run install/installer.py. In a json run its events are relayed through ctx.progress (stdout is the event stream); otherwise it prints as it always did.
    Returns (exit status, the lines it printed when they were captured)."""
    if ctx.root and "--stage-only" not in args and "--dry-run" not in args:
        raise RuntimeError(
            "the GRUB installer writes to the real system and cannot work in a staged tree (--root): use --grub-stage-only to build the theme"
        )
    env = dict(os.environ, MATERIAL_BOOT_UNIFIED="1")
    cmd = [sys.executable, str(HERE / "install/installer.py"), *args]
    if not ctx.json:
        return subprocess.run(cmd, env=env).returncode, []
    p = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, text=True)
    lines = []
    for line in p.stdout:
        lines.append(line.rstrip("\n"))
        try:
            ev = json.loads(line)
        except ValueError:
            ev = None
        if isinstance(ev, dict) and "event" in ev:
            if ev["event"] != "done":  # the core says when everything is done
                ctx.progress(ev)
        else:
            ctx.progress({"event": "log", "text": line.rstrip("\n")})
    return p.wait(), lines


def hook_detect(ctx):
    f = mgdetect.detect(ctx.root, ctx.target_version)
    d = f.as_dict()
    d["found"] = f.kind != "none"
    d["old_names"] = list(f.old_names)
    return d


def hook_plan(ctx):
    """What a run would do: the engine's own dry run (it builds in a scratch directory and writes nothing to the system)."""
    rc, lines = _capture(ctx, engine_args(ctx, "--dry-run"))
    if rc:
        raise RuntimeError("the dry run failed:\n" + "\n".join(lines[-15:]))
    return [ln for ln in lines if ln.strip()]


def _capture(ctx, args):
    env = dict(os.environ, MATERIAL_BOOT_UNIFIED="1")
    r = subprocess.run(
        [sys.executable, str(HERE / "install/installer.py"), *args], env=env, capture_output=True, text=True
    )
    return r.returncode, (r.stdout + r.stderr).splitlines()


def hook_install(ctx):
    if ctx.dry_run:
        return {"changed": False, "notes": hook_plan(ctx)}
    rc, _ = run_engine(ctx, engine_args(ctx))
    if rc:
        raise RuntimeError(
            f"the Material GRUB installer failed (exit status {rc}); its output is above, and GRUB was left working as before"
        )
    if ctx.options.get(
        "stage-only"
    ):  # built, not installed: the state record must not say it is (the core honours `record`)
        return {"changed": False, "record": False, "notes": ["the theme was built and not installed (stage-only)"]}
    return {"changed": True, "notes": []}


def hook_verify(ctx):
    if ctx.options.get("stage-only") or ctx.options.get("ventoy") or ctx.dry_run:
        return []
    f = mgdetect.detect(ctx.root, ctx.target_version)
    if f.kind == "none":
        return ["Material GRUB is not installed after the install"]
    return [f"missing after the install: {m}" for m in f.missing]


def hook_uninstall(ctx):
    if ctx.dry_run:
        return {"changed": False}
    rc, _ = run_engine(ctx, ["--yes", "--no-tui", "--uninstall"] + (["--progress", "json"] if ctx.json else []))
    if rc:
        raise RuntimeError(f"the uninstall failed (exit status {rc}); its output is above")
    return {"changed": True}


def hook_doctor(ctx):
    exe = _material_grub()
    if not exe:
        return [("info", "the material-grub command is not installed here, so its checks were not run")]
    r = subprocess.run([exe, "doctor"], capture_output=True, text=True)
    out = [ln for ln in r.stdout.splitlines() if ln.strip()]
    return [("fail" if r.returncode else "ok", ln) for ln in out] or [
        ("fail" if r.returncode else "ok", "material-grub doctor printed nothing")
    ]


def _material_grub():
    return shutil.which("material-grub")


def main(argv, core):
    """`material-boot grub <command>`: the commands are material-grub's own, run by its own front end (same messages and exit codes)."""
    exe = _material_grub()
    if not exe:
        print("Material GRUB is not installed: run `material-boot core install --with grub`.", file=sys.stderr)
        return 1
    return subprocess.run([exe, *argv]).returncode
