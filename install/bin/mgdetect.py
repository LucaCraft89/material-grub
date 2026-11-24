"""Is Material GRUB already installed here, which version, how, and what is the right thing to do about it? stdlib only.

The installer, the packages' scriptlets (they run the installer) and `material-grub doctor` all ask this module, so they never disagree.

  detect(root, target)           -> Finding: what is installed under `root` ("" is the real system), against the version about to be installed
  notice(finding, target)        -> the lines the user is shown before anything changes
  policy(finding, target, how)   -> (ok, message): refuse a downgrade, or a source install over a package's files
  record(root, ...) / read(root) the state record, /var/lib/material-grub/state.json

The state record says which parts are installed, with their versions, and how (`package`, `source`, `immutable`). Installs made before it existed
(0.7.x and older) are recognised by their files (the fingerprints in FILES) and get a record at their next install or update.
"""

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import mgplugins
import mgrub

STATE_VERSION = 1
# relative to the root of the system; a normal (non-immutable) install
FILES = {
    "package": "usr/share/material-grub/VERSION",
    "command": "usr/local/bin/material-grub",
    "hook05": "etc/grub.d/05_material",
    "hook15": "etc/grub.d/15_material_menu",
    "hook90": "etc/grub.d/90_material_system",
    "postprocess": "usr/libexec/material-grub-postprocess",
    "path unit": "etc/systemd/system/material-grub.path",
}
IMMUTABLE_FILES = {
    "package": "var/lib/material-grub/pkg/VERSION",
    "command": "usr/local/bin/material-grub",
    "postprocess": "var/lib/material-grub/postprocess",
    "path unit": "etc/systemd/system/material-grub.path",
}
OLD_NAMES = ("usr/local/bin/material-grub-apply", "usr/local/sbin/material-grub-apply", "usr/local/sbin/material-grub")


def version_tuple(v):
    """'0.8.0' -> (0, 8, 0); anything that is not numbers (a git describe, '?') compares as the lowest version."""
    out = []
    for part in str(v or "").split("."):
        m = re.match(r"^\d+", part)
        if not m:
            break
        out.append(int(m.group()))
    return tuple(out) or (0,)


def _state_dir(root):
    return (
        Path(root) / "var/lib/material-grub"
        if root
        else Path(os.environ.get("MATERIAL_STATE_DIR", "/var/lib/material-grub"))
    )


def state_path(root=""):
    return _state_dir(root) / "state.json"


def read(root=""):
    """The state record, or None (no record, or one that cannot be read: it is only ever an extra, never a reason to fail)."""
    try:
        d = json.loads(state_path(root).read_text())
        return d if isinstance(d, dict) and d.get("state") == STATE_VERSION else None
    except (OSError, ValueError):
        return None


def write(root, data):
    """Atomically replace the state record."""
    import tempfile

    p = state_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".state.")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, p)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def record(root, version, how, layout, parts=None, now=None, previous=None):
    """Write the state record after an install or update. `parts`: {name: version or dict}; keys another part wrote (Plymouth's `changes`) are kept."""
    old = read(root) or {}
    data = dict(old)
    data.update({"state": STATE_VERSION, "version": version, "how": how, "layout": layout})
    merged = dict(old.get("parts") or {})
    merged.update(parts or {})
    data["parts"] = merged
    stamp = now or time.strftime("%Y-%m-%dT%H:%M:%S%z")
    data["installed_at"] = stamp
    hist = list(old.get("history") or [])[-19:]
    prev = previous if previous is not None else old.get("version")
    if prev != version:
        hist.append({"from": prev, "to": version, "at": stamp})
    data["history"] = hist
    write(root, data)
    return data


class Finding:
    """What is installed. kind: none | unknown | older | same | newer (against the version being installed)."""

    def __init__(self):
        self.kind = "none"
        self.version = None
        self.layout = "normal"
        self.how = "unknown"  # package:rpm | package:deb | package:pacman | source | unknown
        self.parts = {}
        self.missing = []  # pieces of an install that are not there
        self.details = []  # sentences for the notice: style, overrides, GUI, ...
        self.state = None
        self.legacy = False  # found by its files: there is no state record yet
        self.old_names = []

    def as_dict(self):
        return {
            "kind": self.kind,
            "version": self.version,
            "layout": self.layout,
            "how": self.how,
            "parts": self.parts,
            "missing": self.missing,
            "details": self.details,
            "legacy": self.legacy,
        }


def owner_of(path):
    """Which package owns `path`: 'package:rpm' | 'package:deb' | 'package:pacman', 'source' when the tools exist and none claims it, 'unknown' without tools."""
    asked = False
    for name, cmd in (
        ("rpm", ["rpm", "-qf", str(path)]),
        ("deb", ["dpkg", "-S", str(path)]),
        ("pacman", ["pacman", "-Qo", str(path)]),
    ):
        if shutil.which(cmd[0]) is None:
            continue
        asked = True
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode == 0:
            return "package:" + name
    return "source" if asked else "unknown"


def detect(root="", target=None, owner=None):
    """Look at the system under `root`, against `target`, the version about to be installed (None: kind is only none or unknown). `owner(path)` is how
    the owner of a file is asked (tests replace it)."""
    r = Path(root or "/")
    owner = owner or (owner_of if not root else (lambda _p: "unknown"))  # a staged root has no package database to ask
    f = Finding()
    f.state = read(root)
    imm = (r / "var/lib/material-grub/env").is_file() and "MG_IMMUTABLE=1" in (
        r / "var/lib/material-grub/env"
    ).read_text(errors="ignore")
    f.layout = "immutable" if imm or (f.state or {}).get("layout") == "immutable" else "normal"
    files = IMMUTABLE_FILES if f.layout == "immutable" else FILES
    present = {k: (r / v).exists() for k, v in files.items()}
    conf = r / "etc/material-grub.conf"
    theme = any((r / d).is_dir() for d in ("boot/grub2/themes/material", "boot/grub/themes/material"))
    f.old_names = [n for n in OLD_NAMES if (r / n).exists()]
    anything = any(present.values()) or theme or bool(f.state)
    if not anything:
        return f  # kind "none": settings left behind by an uninstall are not an install
    f.legacy = f.state is None
    f.kind = "unknown"
    ver = None
    try:
        ver = (r / files["package"]).read_text().strip() or None
    except OSError:
        pass
    ver = ver or (f.state or {}).get("version")
    f.version = ver
    if ver and target:
        a, b = version_tuple(ver), version_tuple(target)
        f.kind = "same" if a == b else "older" if a < b else "newer"
    f.missing = [k for k, ok in present.items() if not ok] + ([] if theme else ["theme"])
    f.how = (f.state or {}).get("how") or "unknown"
    if f.how == "unknown":
        if f.layout == "immutable":
            f.how = "immutable"
        elif present["package"]:
            f.how = owner(r / files["package"])
    f.parts = dict((f.state or {}).get("parts") or {})
    if present["package"] and ver:
        f.parts.setdefault("core", ver)
    if (r / "usr/share/material-grub-gui").is_dir():
        f.parts.setdefault("gui", ver or "?")
    plug_dirs = [r / d.lstrip("/") for d in mgplugins.DEFAULT_DIRS] if root else None
    for p in mgplugins.discover((), plug_dirs):
        f.parts.setdefault(p.name, p.version if not p.problem else f"{p.version} (not usable)")
    if conf.is_file():
        c = mgrub.load_conf(str(conf))
        f.details.append(f"style {c['STYLE']}, scheme {c['SCHEME']}")
    try:
        import mgoverrides

        ov, _ = mgoverrides.load(r / "etc/material-grub/overrides.json")
        n = len(ov["entries"])
        extra = (["one seed colour"] if ov["seed"]["mode"] == "single" else []) + (
            [f"{n} customised entr" + ("y" if n == 1 else "ies")] if n else []
        )
        if extra:
            f.details.append(", ".join(extra))
    except Exception:  # a bad overrides file is reported by doctor, not here
        pass
    if "gui" in f.parts:
        f.details.append("GUI installed")
    return f


HOW_TEXT = {
    "package:rpm": "an rpm package",
    "package:deb": "a deb package",
    "package:pacman": "a pacman package",
    "source": "a source install",
    "immutable": "a source install, immutable layout",
    "package:unknown": "a package",
    "unknown": "an install of unknown origin",
}


def notice(f, target):
    """The lines shown before anything is changed. Empty when there is no install."""
    if f.kind == "none":
        return []
    head = f"Found Material GRUB {f.version or '(unknown version)'}, {HOW_TEXT.get(f.how, f.how)}"
    if f.layout == "immutable" and f.how != "immutable":
        head += ", immutable layout"
    out = [head + ("" if not f.details else ": " + "; ".join(f.details)) + "."]
    others = [f"{k} {v}" for k, v in sorted(f.parts.items()) if k not in ("core", "grub")]
    if others:
        out.append("Other parts installed: " + ", ".join(others) + ".")
    if f.kind == "older":
        out.append(
            f"This will update it to {target}. Your settings (options, colours, entries, icons, presets) are kept."
        )
    elif f.kind == "same":
        out.append(f"It is the same version as this one ({target}): it will be installed again, keeping your settings.")
    elif f.kind == "newer":
        out.append(f"That is NEWER than this one ({target}).")
    else:
        out.append("Its version cannot be read; it will be replaced by " + target + ", keeping your settings.")
    if f.missing and f.kind != "newer":
        out.append("Pieces that are missing and will be put back: " + ", ".join(f.missing) + ".")
    if f.legacy:
        out.append("It has no state record yet (it was installed by an older version): one is written now.")
    if f.old_names:
        out.append("Old command names will be removed: " + ", ".join("/" + n for n in f.old_names) + ".")
    return out


def policy(f, target, how, force=False):
    """(ok, message). `how` is how THIS run installs: 'package' (a package scriptlet) or 'source'."""
    if f.kind == "none":
        return True, ""
    if f.kind == "newer" and not force:
        return False, (
            f"Material GRUB {f.version} is installed and this is {target}. Installing an older version over a newer one can leave "
            "settings that it does not understand (newer options, presets, overrides). Update to the newer version instead, "
            "or run with --force if you really mean it."
        )
    if how == "source" and f.how.startswith("package:") and not force:
        cmd = {
            "package:rpm": "sudo dnf upgrade material-grub   (or the package manager you installed it with)",
            "package:deb": "sudo apt install --only-upgrade material-grub",
            "package:pacman": "sudo pacman -Syu material-grub",
        }.get(f.how, "update it with the package manager you installed it with")
        return False, (
            f"Material GRUB is installed from {HOW_TEXT.get(f.how, 'a package')}, and a source install would fight your package manager over the same files. "
            f"Update it the usual way:\n    {cmd}\nor remove the package first. --force overrides this."
        )
    return True, ""


def adopting(f, how):
    """True when a package install takes over a source install (its files are replaced, settings kept)."""
    return how == "package" and f.kind != "none" and f.how in ("source", "immutable", "unknown")
