"""What the GUI shows: the system's state read as a normal user (config, overrides, entries, catalog) plus the checks for what the GUI sends back.
stdlib only (the shared modules are imported after mgpaths.setup())."""

import copy
import json
from pathlib import Path

import mgoverrides
import mgpresets
import mgrub
import mgsafe
import mgseeds

DEMO = [  # shown when the machine has no entry state yet (not installed here, or a fresh checkout)
    {
        "class": "mg_demo000001",
        "key": "fedora",
        "kind": "kernel",
        "level": "top",
        "title": "Fedora Linux (6.12.1)",
        "kver": "6.12.1",
        "os": "Fedora Linux",
    },
    {"class": "mg_demo000002", "key": "ubuntu", "kind": "kernel", "level": "top", "title": "Ubuntu", "os": "Ubuntu"},
    {"class": "mg_demo000003", "key": "windows11", "kind": "plain", "level": "top", "title": "Windows Boot Manager"},
    {"class": "mg_demo000004", "key": "firmware", "kind": "plain", "level": "top", "title": "UEFI Firmware Settings"},
]

CONF_KEYS = (
    "STYLE",
    "COOKIE",
    "LOGO",
    "HINTS",
    "RAW_NAME",
    "COUNTDOWN",
    "TIMEOUT",
)  # what the GUI may change (SCHEME is baked at build time)


def _json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def catalog(pkg):
    """key -> {title, subtitle, aliases, glyph} from the package."""
    if pkg is None:
        return {}
    titles = _json(pkg / "titles.json", {})
    subs = _json(pkg / "subtitles.json", {})
    classes = _json(pkg / "classes.json", {})
    pal = _json(pkg / "palettes.json", {})
    return {
        k: {
            "title": t,
            "subtitle": subs.get(k, ""),
            "aliases": classes.get(k, [k]),
            "glyph": (pkg / "glyphs" / f"{k}.png").is_file(),
            "seed": pal.get(k, {}).get("seed"),
        }
        for k, t in titles.items()
    }


def entries():
    """(entries, menu, demo): the machine's real boot entries as the last apply saw them, else a small demo set."""
    sd = mgsafe.state_dir()
    ents = _json(sd / "entries.json", [])
    if not ents:
        return copy.deepcopy(DEMO), [{"level": "top", "items": [e["class"] for e in DEMO]}], True
    return ents, _json(sd / "menu.json", []), False


def overrides_icons(ov_path=None):
    """Names of the pictures already in the icons folder."""
    d = mgoverrides.icon_dir(Path(ov_path) if ov_path else None)
    try:
        return sorted(f.name for f in d.iterdir() if f.suffix.lower() in mgoverrides.IMAGE_EXT)
    except OSError:
        return []


def installed_version(pkg):
    try:
        return (pkg / "VERSION").read_text().strip() if pkg else None
    except OSError:
        return None


def read_state(pkg):
    ov, problems = mgoverrides.load()
    ents, menu, demo = entries()
    conf = mgrub.load_conf()
    scheme = "dark"
    try:
        scheme = (pkg / "scheme.txt").read_text().strip() if pkg else "dark"
    except OSError:
        pass
    return {
        "version": installed_version(pkg),
        "installed": pkg is not None,
        "scheme": scheme,
        "conf": {k: conf[k] for k in CONF_KEYS},
        "overrides": ov,
        "problems": problems,
        "entries": ents,
        "menu": menu,
        "demo": demo,
        "icons": overrides_icons(),
        "catalog": catalog(pkg),
        "seeds": [{"name": n, "color": h} for n, h in mgseeds.SEEDS],
        "groups": list(mgoverrides.GROUPS),
        "choices": {k: list(v) for k, v in mgrub.CONF_CHOICES.items() if k in CONF_KEYS},
    }


def check_draft(draft):
    """Validate what the GUI wants to apply: {conf: {...}, overrides: {...}}. Returns (clean, errors)."""
    errs = []
    if not isinstance(draft, dict):
        return None, ["the request must be an object"]
    conf = draft.get("conf", {})
    clean_conf = {}
    if not isinstance(conf, dict):
        errs.append("conf must be an object")
        conf = {}
    for k, v in conf.items():
        if k not in CONF_KEYS or not mgrub._conf_ok(k, str(v)):
            errs.append(f"conf: {k}={v!r} is not allowed")
        else:
            clean_conf[k] = str(v)
    ov, oerrs, _ = mgoverrides.validate(draft.get("overrides", {}))
    errs += oerrs
    return ({"conf": clean_conf, "overrides": ov}, []) if not errs else (None, errs)


def preset_dir(home_config):
    return Path(home_config) / "presets"


def presets_list(cfg_dir):
    return mgpresets.listing(Path(cfg_dir) / "overrides.json")
