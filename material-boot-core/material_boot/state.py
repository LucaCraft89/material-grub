"""The state record of an install, and who owns a file. stdlib only.

Moved verbatim from material-grub's mgdetect.py (release/0.8.0, 588f909); tests/test_provenance.py checks that. The record, /var/lib/material-grub/state.json,
says which parts are installed, with their versions, and how (`package`, `source`, `immutable`); installs made before it existed are recognised by the files
the GRUB part knows about (its `detect` stays in material-grub until it becomes the GRUB part's detect hook). `version_tuple` here is the LENIENT one (anything
that is not numbers compares as the lowest version, so a git describe never raises); material_boot.plugins.version_tuple is the strict one.
"""

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

STATE_VERSION = 1


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
