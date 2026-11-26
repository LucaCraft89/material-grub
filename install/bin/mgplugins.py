"""Compatibility name: the plugin loader moved to material-boot-core (material_boot.plugins, plugin API 2). This front end keeps the names it called, and adds
the one thing only it knows: the names of its own built-in commands (`reserved`), which a part may not take over."""

import json
from pathlib import Path

import mgcore  # noqa: F401  (puts material-boot-core on sys.path)
from material_boot import plugins as _p

CORE_API = _p.CORE_API
DEFAULT_DIRS = _p.DEFAULT_DIRS
search_dirs = _p.search_dirs
read_manifest = _p.read_manifest


def _mark(parts, reserved):
    for p in parts:
        if p.name in reserved and not p.problem:
            p.problem = f"'{p.name}' is a built-in command of material-grub and cannot be taken over by a part"
    return parts


def _staged(parts, root):
    """A staged tree (a test, `doctor --root`) has the entry file under the root, not at its absolute path on this machine."""
    for p in parts:
        if root and p.problem and "entry file" in p.problem:
            try:
                entry = json.loads(Path(p.path).read_text()).get("entry")
            except (OSError, ValueError):
                continue
            if isinstance(entry, str) and entry.startswith("/") and (Path(root) / entry.lstrip("/")).is_file():
                p.problem, p.entry = None, str(Path(root) / entry.lstrip("/"))
    return parts


def discover(reserved=(), dirs=None, root=""):
    return _mark(_staged(_p.discover(dirs), root), reserved)


def usable(reserved=()):
    return [p for p in discover(reserved) if not p.problem]


def find(name, reserved=()):
    for p in discover(reserved):
        if p.name == name:
            return p
    return None


def run(rec, argv, core):
    return _p.run(rec, argv, core)
