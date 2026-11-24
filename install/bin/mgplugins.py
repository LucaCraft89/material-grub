"""Optional parts of Material GRUB that live in other packages (material-plymouth is the first). stdlib only.

A part announces itself by dropping ONE manifest into a plugin directory; nothing in this package knows its code. A part that is not installed has
no manifest, so it has no sub-command, no menu entry and no line in `doctor`. A broken or incompatible manifest never breaks `material-grub`:
it is reported (`doctor`) and the rest keeps working.

    <plugin dir>/<name>.json
    {
      "manifest": 1,
      "name": "plymouth",                         # the sub-command: `material-grub plymouth ...`
      "title": "Plymouth boot splash",
      "version": "0.1.0",
      "core_api": 1,                              # the plugin API this part was written for (CORE_API below)
      "entry": "/usr/share/material-plymouth/bin/mgplugin.py",   # absolute path of a Python file that defines main(argv, core) -> int
      "summary": "boot splash that continues the GRUB theme",
      "menu": [["Apply the Plymouth theme", "Render it and rebuild the initramfs", ["plymouth", "apply"]]]   # optional entries of the menu
    }

Plugin directories: $MATERIAL_PLUGIN_PATH (os.pathsep separated, used by the tests and by checkouts), else /usr/share/material-boot/plugins.d and
/usr/local/share/material-boot/plugins.d. See docs/plugins.md for the contract.
"""

import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

CORE_API = 1
NAME = re.compile(r"^[a-z][a-z0-9-]{1,19}$")
DEFAULT_DIRS = ("/usr/share/material-boot/plugins.d", "/usr/local/share/material-boot/plugins.d")
MAX_MANIFEST = 64 * 1024


def search_dirs():
    env = os.environ.get("MATERIAL_PLUGIN_PATH")
    return [Path(d) for d in (env.split(os.pathsep) if env is not None else DEFAULT_DIRS) if d]


def _clean_menu(menu):
    out = []
    for m in menu if isinstance(menu, list) else []:
        if (
            isinstance(m, list)
            and len(m) == 3
            and isinstance(m[0], str)
            and isinstance(m[1], str)
            and isinstance(m[2], list)
            and m[2]
            and all(isinstance(a, str) for a in m[2])
        ):
            out.append((m[0], m[1], m[2]))
    return out


def read_manifest(path, reserved=()):
    """One manifest file -> a plugin record (SimpleNamespace). `problem` is None when it is usable, else a sentence for `doctor`. Never raises."""
    path = Path(path)
    rec = SimpleNamespace(
        name=path.stem, title=path.stem, version="?", entry=None, summary="", menu=[], path=path, problem=None
    )
    try:
        if path.stat().st_size > MAX_MANIFEST:
            raise ValueError("the manifest is too large")
        m = json.loads(path.read_text())
        if not isinstance(m, dict):
            raise ValueError("the manifest must be a JSON object")
    except (OSError, ValueError) as e:
        rec.problem = f"cannot read {path}: {e}"
        return rec
    name = m.get("name")
    if not isinstance(name, str) or not NAME.match(name):
        rec.problem = f"{path}: 'name' must be 2 to 20 characters: a letter, then lowercase letters, digits or '-'"
        return rec
    rec.name = name
    rec.title = m.get("title") if isinstance(m.get("title"), str) else name
    rec.version = str(m.get("version", "?"))[:40]
    rec.summary = m.get("summary") if isinstance(m.get("summary"), str) else ""
    rec.menu = _clean_menu(m.get("menu"))
    if name in reserved:
        rec.problem = f"{path}: '{name}' is a built-in command and cannot be taken over by a plugin"
    elif m.get("manifest") != 1:
        rec.problem = f"{path}: unknown manifest version {m.get('manifest')!r}"
    elif m.get("core_api") != CORE_API:
        rec.problem = (
            f"{name} {rec.version} was written for plugin API {m.get('core_api')!r}, this material-grub has {CORE_API}: "
            "update whichever of the two is older"
        )
    elif not isinstance(m.get("entry"), str) or not os.path.isabs(m["entry"]) or not Path(m["entry"]).is_file():
        rec.problem = f"{name}: its entry file {m.get('entry')!r} is missing (is the package half removed?)"
    else:
        rec.entry = m["entry"]
    return rec


def discover(reserved=(), dirs=None):
    """Every plugin found in the plugin directories, usable or not, ordered by name. The first manifest of a name wins (earlier directories first)."""
    found = {}
    for d in dirs if dirs is not None else search_dirs():
        try:
            files = sorted(d.glob("*.json"))
        except OSError:
            continue
        for f in files:
            rec = read_manifest(f, reserved)
            if rec.name not in found:
                found[rec.name] = rec
    return [found[k] for k in sorted(found)]


def usable(reserved=()):
    return [p for p in discover(reserved) if p.problem is None]


def find(name, reserved=()):
    return next((p for p in discover(reserved) if p.name == name), None)


def load(rec):
    """Import the plugin's entry file. Raises ImportError with a readable message when it cannot be loaded or has no main()."""
    spec = importlib.util.spec_from_file_location(f"mgplugin_{rec.name.replace('-', '_')}", rec.entry)
    if spec is None or spec.loader is None:
        raise ImportError(f"{rec.entry} is not a Python file")
    mod = importlib.util.module_from_spec(spec)
    here = str(Path(rec.entry).resolve().parent)
    sys.path.insert(1, here)  # the plugin's own modules sit next to its entry file
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        raise ImportError(f"{rec.name}: cannot load {rec.entry}: {e}") from e
    finally:
        if here in sys.path:
            sys.path.remove(here)
    if not callable(getattr(mod, "main", None)):
        raise ImportError(f"{rec.name}: {rec.entry} defines no main(argv, core)")
    return mod


def run(rec, argv, core):
    """Run the plugin's main(argv, core) and return its exit status (an int; None counts as 0). A crash is reported, not raised."""
    try:
        mod = load(rec)
    except ImportError as e:
        print(f"material-grub: {e}", file=sys.stderr)
        return 1
    try:
        rc = mod.main(list(argv), core)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # a plugin bug must not look like a material-grub bug
        print(f"material-grub: the {rec.name} plugin failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return rc if isinstance(rc, int) else 0
