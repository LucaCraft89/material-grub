#!/usr/bin/env python3
"""material-grub-gui-helper: the only thing the GUI runs as root (through pkexec, see org.material-grub.gui.policy).

It reads ONE JSON request on stdin and prints one JSON event per line on stdout (the same events as `install.sh --progress json`:
step, info, ok, warn, error, log, done). It takes no arguments and no environment: what it may do is the fixed list of verbs below, and every
value is validated again here, because the caller is an unprivileged program.

  apply   {"verb": "apply", "conf": {...}, "overrides": {...}, "icons": {"name.png": "<base64>"}}
          backs up the current files, writes icons, overrides.json and the runtime options, runs material-grub-apply, restores the backup if that fails.
  update  {"verb": "update"}  updates Material GRUB through the system's package manager (package installs) or reruns the installer (source installs)

Only when NOT running as root (the tests) may MG_HELPER_ROOT point all paths into a scratch directory; as root the environment is ignored.
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def find_modules():
    """The shared modules (mgrub, mgoverrides, ...): next to this file in a checkout, else in the installed package."""
    here = Path(__file__).resolve().parent
    for c in (
        here.parent / "install/bin",
        Path("/usr/share/material-grub/bin"),
        Path("/var/lib/material-grub/pkg/bin"),
    ):
        if (c / "mgoverrides.py").is_file():
            return c
    return None


MODS = find_modules()
if MODS is None:
    print(
        json.dumps(
            {
                "event": "error",
                "msg": "material-grub is not installed (or too old: it has no overrides support)",
                "code": 1,
            }
        )
    )
    sys.exit(1)
sys.path.insert(0, str(MODS))
import mgoverrides  # noqa: E402
import mgrub  # noqa: E402

TEST = os.geteuid() != 0 and os.environ.get("MG_HELPER_ROOT")
ROOT = Path(os.environ["MG_HELPER_ROOT"]) if TEST else Path("/")
MAX_ICON = 4 * 1024 * 1024
MAX_REQUEST = 64 * 1024 * 1024
CONF_KEYS = ("STYLE", "COOKIE", "LOGO", "HINTS", "RAW_NAME", "COUNTDOWN", "TIMEOUT")
t0 = time.time()


def p(path):
    return ROOT / str(path).lstrip("/")


CONF = p("/etc/material-grub.conf")
OVERRIDES = p("/etc/material-grub/overrides.json")
ICONS = OVERRIDES.parent / "icons"
BACKUPS = p("/var/backups/material-grub")
APPLY = os.environ.get("MG_HELPER_APPLY") if TEST else "/usr/local/sbin/material-grub-apply"


def emit(event, **kw):
    print(json.dumps({"event": event, "t": round(time.time() - t0, 1), **kw}), flush=True)


def die(msg, code=1):
    emit("error", msg=msg, code=code)
    emit("done", rc=code, ok=False)
    sys.exit(code)


def run(cmd, label):
    """Run a command, turning its output into log events. Returns its exit status."""
    emit("info", msg=label)
    proc = subprocess.Popen(
        cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace"
    )
    with proc.stdout:
        for line in proc.stdout:
            if line.strip():
                emit("log", text=line.rstrip(), level="info")
    return proc.wait()


def check_icon(name, raw):
    if not mgoverrides._icon_ok("file:" + name):
        raise ValueError(f"bad icon name {name!r}")
    if len(raw) > MAX_ICON:
        raise ValueError(f"{name} is larger than {MAX_ICON // 1024 // 1024} MB")
    if name.lower().endswith(".svg"):
        head = raw[:4096].lstrip().lower()
        if b"<svg" not in raw[:65536].lower() and not head.startswith(b"<?xml"):
            raise ValueError(f"{name} is not an SVG file")
        return
    try:
        import io

        from PIL import Image

        im = Image.open(io.BytesIO(raw))
        im.verify()
        if im.width * im.height > 50_000_000:
            raise ValueError("picture is too large")
    except ImportError:
        pass  # Pillow is a dependency of the theme tools; without it the picture is checked when it is used
    except Exception as e:
        raise ValueError(f"{name} is not a readable picture ({e})") from None


def backup():
    d = BACKUPS / ("gui-" + time.strftime("%Y%m%d-%H%M%S"))
    d.mkdir(parents=True, exist_ok=True)
    for f in (CONF, OVERRIDES):
        if f.is_file():
            shutil.copy2(f, d / f.name)
    if ICONS.is_dir():
        shutil.copytree(ICONS, d / "icons", dirs_exist_ok=True)
    return d


def restore(d):
    for f in (CONF, OVERRIDES):
        if (d / f.name).is_file():
            shutil.copy2(d / f.name, f)
        elif f.exists():
            f.unlink()
    if (d / "icons").is_dir():
        shutil.rmtree(ICONS, ignore_errors=True)
        shutil.copytree(d / "icons", ICONS)


def verb_apply(req):
    conf = req.get("conf", {})
    if not isinstance(conf, dict) or any(k not in CONF_KEYS or not mgrub._conf_ok(k, str(v)) for k, v in conf.items()):
        die("the request has an option that is not allowed")
    ov, errs, _ = mgoverrides.validate(req.get("overrides", {}))
    if errs:
        die("the overrides are not valid: " + "; ".join(errs))
    icons = {}
    for name, b in (req.get("icons") or {}).items():
        try:
            raw = base64.b64decode(b, validate=True)
            check_icon(name, raw)
        except (ValueError, TypeError) as e:
            die(str(e))
        icons[name] = raw
    for r in ov["entries"]:  # every picture a rule points to must exist after this write
        ic = r.get("icon", "")
        if ic.startswith("file:") and ic[5:] not in icons and not (ICONS / ic[5:]).is_file():
            die(f"the picture {ic[5:]} was not sent and is not installed")
    emit("step", n=1, total=4, msg="Saving a backup of the current settings")
    b = backup()
    emit("ok", msg=f"backup in {b}")
    emit("step", n=2, total=4, msg="Writing your customisations")
    try:
        if icons:
            ICONS.mkdir(parents=True, exist_ok=True)
            for name, raw in icons.items():
                (ICONS / name).write_bytes(raw)
        mgoverrides.save(ov, OVERRIDES)
        if conf:
            mgrub.write_conf(CONF, {k: str(v) for k, v in conf.items()})
    except (OSError, ValueError) as e:
        restore(b)
        die(f"could not write the settings ({e}); the previous ones are back")
    emit("ok", msg="settings written")
    emit("step", n=3, total=4, msg="Applying to GRUB (rebuilding grub.cfg and the scenes)")
    if APPLY:
        rc = run([APPLY], "material-grub-apply")
    else:
        rc = 1
    if rc != 0:
        emit("step", n=4, total=4, msg="Going back to the previous settings")
        restore(b)
        if APPLY:
            run([APPLY], "re-applying the previous settings")
        die("applying failed; your previous settings are back (see the log above)", rc or 1)
    emit("step", n=4, total=4, msg="Done")
    emit("ok", msg="Material GRUB is updated. The new menu shows on the next boot.")
    emit("done", rc=0, ok=True, elapsed=f"{int(time.time() - t0)}s")


def verb_update(req):
    emit("step", n=1, total=2, msg="Looking for how Material GRUB was installed")
    pkg_mgr = None
    for tool, cmd in (
        ("dnf", ["dnf", "-y", "upgrade", "--refresh", "material-grub", "material-grub-gui"]),
        (
            "apt-get",
            ["sh", "-c", "apt-get update && apt-get install -y --only-upgrade material-grub material-grub-gui"],
        ),
        ("pacman", ["pacman", "-Syu", "--noconfirm", "--needed", "material-grub", "material-grub-gui"]),
    ):
        if shutil.which(tool) and installed_by(tool):
            pkg_mgr = (tool, cmd)
            break
    if pkg_mgr is None:
        die("Material GRUB was not installed from a package: update it with git pull and ./install.sh in its folder")
    emit("ok", msg=f"installed with {pkg_mgr[0]}")
    emit("step", n=2, total=2, msg=f"Updating with {pkg_mgr[0]}")
    rc = run(pkg_mgr[1], " ".join(pkg_mgr[1]))
    if rc != 0:
        die("the package manager reported a problem (see the log above); the menu was left as it was", rc)
    emit("ok", msg="updated; the package re-applied the theme")
    emit("done", rc=0, ok=True, elapsed=f"{int(time.time() - t0)}s")


def installed_by(tool):
    q = {
        "dnf": ["rpm", "-q", "material-grub"],
        "apt-get": ["dpkg", "-s", "material-grub"],
        "pacman": ["pacman", "-Q", "material-grub"],
    }[tool]
    return shutil.which(q[0]) is not None and subprocess.run(q, capture_output=True).returncode == 0


VERBS = {"apply": verb_apply, "update": verb_update}


def main():
    raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
    if len(raw) > MAX_REQUEST:
        die("the request is too large")
    try:
        req = json.loads(raw)
    except ValueError:
        die("the request is not JSON")
    verb = req.get("verb") if isinstance(req, dict) else None
    if verb not in VERBS:
        die(f"unknown request {verb!r}")
    VERBS[verb](req)
    return 0


if __name__ == "__main__":
    sys.exit(main())
