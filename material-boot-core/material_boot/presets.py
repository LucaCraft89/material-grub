"""Presets: the look you built (overrides.json plus the runtime options of /etc/material-grub.conf) saved under a name, applied again later, or
moved to another machine as one JSON file. stdlib only.

A preset file: {"preset": 1, "name": "...", "conf": {"STYLE": "list", ...}, "overrides": {...}, "icons": {"logo.png": "<base64>"}}
The colour scheme (dark or light) and the resolution are baked at build time and are not part of a preset.
"""

import base64
import json
import os
import re
from pathlib import Path

# the names of the modules are kept as they were in material-grub, so the bodies below are the original ones
from . import conf as mgrub  # noqa: E402  (load_conf, write_conf, _conf_ok)
from . import overrides as mgoverrides  # noqa: E402

FORMAT = 1
CONF_KEYS = (
    "STYLE",
    "COOKIE",
    "LOGO",
    "HINTS",
    "RAW_NAME",
    "COUNTDOWN",
    "TIMEOUT",
    "PLYMOUTH",
    "PLYMOUTH_BAR",
    "PLYMOUTH_MOTION",
)
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.()-]{0,39}$")
MAX_ICON = 2 * 1024 * 1024


def preset_dir(ov_path=None):
    return (Path(ov_path) if ov_path else mgoverrides.path()).parent / "presets"


def check_name(name):
    if not isinstance(name, str) or not NAME.match(name):
        raise ValueError(
            "a preset name is 1 to 40 letters, digits, spaces or _ . ( ) -, starting with a letter or digit"
        )
    return name


def make(name, conf, ov, icon_dir):
    """The preset dict for a given look (runtime options `conf`, validated overrides `ov`). Pictures from `icon_dir` the overrides use are embedded."""
    icons = {}
    for r in ov["entries"]:
        ic = r.get("icon", "")
        if ic.startswith("file:"):
            f = Path(icon_dir) / ic[5:]
            try:
                if f.stat().st_size <= MAX_ICON:
                    icons[ic[5:]] = base64.b64encode(f.read_bytes()).decode()
            except OSError:
                pass
    return {
        "preset": FORMAT,
        "name": check_name(name),
        "conf": {k: str(conf[k]) for k in CONF_KEYS if k in conf},
        "overrides": ov,
        "icons": icons,
    }


def build(name, ov_path=None, conf_path=None):
    """The preset dict for the look installed now."""
    ov_path = Path(ov_path) if ov_path else mgoverrides.path()
    ov, _ = mgoverrides.load(ov_path)
    return make(name, mgrub.load_conf(conf_path), ov, mgoverrides.icon_dir(ov_path))


def validate(data):
    """(clean preset, errors). The overrides and every conf value are checked like when they are written."""
    errs = []
    if not isinstance(data, dict) or data.get("preset") != FORMAT:
        return None, [f'not a preset file (expected "preset": {FORMAT})']
    try:
        check_name(data.get("name"))
    except ValueError as e:
        errs.append(str(e))
    conf = data.get("conf", {})
    if not isinstance(conf, dict) or not all(k in CONF_KEYS and mgrub._conf_ok(k, str(v)) for k, v in conf.items()):
        errs.append("conf has an unknown key or a bad value")
        conf = {}
    ov, oerrs, _ = mgoverrides.validate(data.get("overrides", {}))
    errs += oerrs
    icons = data.get("icons", {})
    clean_icons = {}
    if not isinstance(icons, dict):
        errs.append("icons must be an object")
        icons = {}
    for n, b in icons.items():
        if not mgoverrides._icon_ok("file:" + n):
            errs.append(f"icons: bad file name {n!r}")
            continue
        try:
            raw = base64.b64decode(b, validate=True)
        except (ValueError, TypeError):
            errs.append(f"icons: {n} is not valid base64")
            continue
        if len(raw) > MAX_ICON:
            errs.append(f"icons: {n} is larger than {MAX_ICON // 1024 // 1024} MB")
            continue
        clean_icons[n] = raw
    if errs:
        return None, errs
    return {
        "name": data["name"],
        "conf": {k: str(v) for k, v in conf.items()},
        "overrides": ov,
        "icons": clean_icons,
    }, []


def save(name, ov_path=None, conf_path=None, data=None):
    """Store the current look (or the given preset dict `data`) as presets/<name>.json next to overrides.json."""
    d = preset_dir(ov_path)
    d.mkdir(parents=True, exist_ok=True)
    data = data or build(name, ov_path, conf_path)
    tmp = d / f".{name}.tmp"
    tmp.write_text(json.dumps(data, indent=1) + "\n")
    os.replace(tmp, d / f"{name}.json")
    return d / f"{name}.json"


def listing(ov_path=None):
    """[(name, summary)] of the stored presets, sorted by name; unreadable files are skipped."""
    out = []
    for f in sorted(preset_dir(ov_path).glob("*.json")):
        try:
            d = json.loads(f.read_text())
            out.append(
                (
                    d["name"],
                    {
                        "style": d.get("conf", {}).get("STYLE"),
                        "entries": len(d.get("overrides", {}).get("entries", [])),
                    },
                )
            )
        except (OSError, ValueError, KeyError):
            continue
    return out


def apply(data, ov_path=None, conf_path=None):
    """Make a (validated) preset the current look: pictures, overrides.json, then the conf values. Raises ValueError for a bad preset."""
    clean, errs = validate(data)
    if clean is None:
        raise ValueError("; ".join(errs))
    ov_path = Path(ov_path) if ov_path else mgoverrides.path()
    icons = mgoverrides.icon_dir(ov_path)
    if clean["icons"]:
        icons.mkdir(parents=True, exist_ok=True)
        for n, raw in clean["icons"].items():
            (icons / n).write_bytes(raw)
    mgoverrides.save(clean["overrides"], ov_path)
    if clean["conf"]:
        mgrub.write_conf(conf_path or os.environ.get("MATERIAL_CONF", "/etc/material-grub.conf"), clean["conf"])
    return clean


def load(name, ov_path=None):
    check_name(name)
    return json.loads((preset_dir(ov_path) / f"{name}.json").read_text())


def delete(name, ov_path=None):
    check_name(name)
    (preset_dir(ov_path) / f"{name}.json").unlink()
