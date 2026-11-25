"""User overrides for the theme: /etc/material-grub/overrides.json (path: $MATERIAL_OVERRIDES). stdlib only.

One file drives the TUI, the GUI and the apply step. It is validated strictly when written (validate) and read leniently at boot
(load never raises: a bad file is reported and the defaults are used, so a typo can never stop the menu from coming up).

    {
      "version": 1,
      "seed":    {"mode": "multi" | "single", "color": "#RRGGBB"},          # single: every entry uses this colour
      "groups":  ["linux", "windows", "system"],                              # order of the sections (a subset is fine)
      "order":   [{"key": "windows11"}, {"class": "mg_1a2b3c4d5e"}, ...],    # top-level entries, first to last; the rest follow
      "entries": [ {"match": {"key": "fedora"}, "name": "My Fedora", "color": "#2E7D32", "icon": "tux", "hidden": false}, ... ]
    }

A match is exactly one of {"key": catalog key}, {"class": the entry's mg_ class} or {"title": text found in the entry's title, any case}.
The first rule that matches an entry wins. icon: a catalog key ("tux") or "file:NAME" for a picture in /etc/material-grub/icons/.
"""

import json
import os
import re
from pathlib import Path

VERSION = 1
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
GROUPS = ("linux", "windows", "system")
MATCH_KEYS = ("key", "class", "title")
RULE_KEYS = ("match", "name", "color", "icon", "hidden")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".bmp")
DEFAULTS = {"version": VERSION, "seed": {"mode": "multi", "color": "#0B3D2E"}, "groups": [], "order": [], "entries": []}


def path():
    return Path(os.environ.get("MATERIAL_OVERRIDES", "/etc/material-grub/overrides.json"))


def icon_dir(p=None):
    return (p or path()).parent / "icons"


def _match(m, where, errs):
    if not isinstance(m, dict) or len(m) != 1 or next(iter(m)) not in MATCH_KEYS:
        errs.append(f"{where}: a match is exactly one of {', '.join(MATCH_KEYS)}")
        return None
    k, v = next(iter(m.items()))
    if not isinstance(v, str) or not v.strip() or len(v) > 200:
        errs.append(f"{where}: {k} must be a non-empty text (at most 200 characters)")
        return None
    return {k: v}


def _icon_ok(v):
    if not isinstance(v, str) or not v:
        return False
    if v.startswith("file:"):
        n = v[5:]
        return bool(n) and "/" not in n and "\\" not in n and not n.startswith(".") and n.lower().endswith(IMAGE_EXT)
    return bool(re.fullmatch(r"[a-z0-9_-]{1,40}", v))


def validate(data):
    """(clean data, errors, warnings). Errors make the file unusable for writing; unknown keys are only warnings."""
    errs, warns = [], []
    if not isinstance(data, dict):
        return dict(DEFAULTS), ["the file must contain a JSON object"], warns
    out = {"version": VERSION, "seed": dict(DEFAULTS["seed"]), "groups": [], "order": [], "entries": []}
    v = data.get("version", VERSION)
    if v != VERSION:
        errs.append(f"version {v!r} is not supported (this is version {VERSION})")
    for k in data:
        if k not in out:
            warns.append(f"unknown key {k!r} ignored")
    seed = data.get("seed", {})
    if isinstance(seed, dict):
        mode = seed.get("mode", "multi")
        if mode not in ("multi", "single"):
            errs.append("seed.mode must be multi or single")
        else:
            out["seed"]["mode"] = mode
        if "color" in seed:
            if isinstance(seed["color"], str) and HEX.match(seed["color"]):
                out["seed"]["color"] = seed["color"].upper()
            else:
                errs.append("seed.color must look like #RRGGBB")
    else:
        errs.append("seed must be an object")
    g = data.get("groups", [])
    if isinstance(g, list) and all(x in GROUPS for x in g) and len(set(g)) == len(g):
        out["groups"] = list(g)
    else:
        errs.append(f"groups must be a list of {', '.join(GROUPS)} without repeats")
    o = data.get("order", [])
    if isinstance(o, list):
        for i, m in enumerate(o):
            c = _match(m, f"order[{i}]", errs)
            if c:
                out["order"].append(c)
    else:
        errs.append("order must be a list")
    r = data.get("entries", [])
    if not isinstance(r, list):
        errs.append("entries must be a list")
        r = []
    for i, rule in enumerate(r):
        w = f"entries[{i}]"
        if not isinstance(rule, dict):
            errs.append(f"{w}: must be an object")
            continue
        for k in rule:
            if k not in RULE_KEYS:
                warns.append(f"{w}: unknown key {k!r} ignored")
        m = _match(rule.get("match"), w + ".match", errs)
        if m is None:
            continue
        new = {"match": m}
        if "name" in rule:
            if isinstance(rule["name"], str) and 0 < len(rule["name"].strip()) <= 60 and "\n" not in rule["name"]:
                new["name"] = rule["name"].strip()
            else:
                errs.append(f"{w}.name must be 1 to 60 characters on one line")
        if "color" in rule:
            if isinstance(rule["color"], str) and HEX.match(rule["color"]):
                new["color"] = rule["color"].upper()
            else:
                errs.append(f"{w}.color must look like #RRGGBB")
        if "icon" in rule:
            if _icon_ok(rule["icon"]):
                new["icon"] = rule["icon"]
            else:
                errs.append(
                    f"{w}.icon must be a catalog key or file:NAME with a picture extension ({', '.join(IMAGE_EXT)})"
                )
        if "hidden" in rule:
            if isinstance(rule["hidden"], bool):
                new["hidden"] = rule["hidden"]
            else:
                errs.append(f"{w}.hidden must be true or false")
        out["entries"].append(new)
    return out, errs, warns


def load(p=None):
    """(overrides, problems). Never raises: a missing file is the defaults, a broken one is the defaults plus the reasons."""
    p = Path(p) if p else path()
    if not p.is_file():
        return dict(DEFAULTS), []
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError) as e:
        return dict(DEFAULTS), [f"{p}: cannot be read ({e})"]
    clean, errs, warns = validate(data)
    if errs:
        return dict(DEFAULTS), [f"{p}: {e}" for e in errs]
    return clean, [f"{p}: {w}" for w in warns]


def save(data, p=None):
    """Validate, then write atomically (0644). Raises ValueError with every problem when the data is not valid."""
    import tempfile

    p = Path(p) if p else path()
    clean, errs, _ = validate(data)
    if errs:
        raise ValueError("; ".join(errs))
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".overrides.")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(clean, f, indent=1)
            f.write("\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, str(p))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def layout_sha(ov):
    """Fingerprint of what only a fresh grub.cfg can apply (hidden entries, their order and the section order). doctor compares it with the
    one recorded when grub.cfg was last generated."""
    import hashlib

    hidden = [r["match"] for r in ov["entries"] if r.get("hidden")]
    return hashlib.sha1(json.dumps([ov["groups"], ov["order"], hidden], sort_keys=True).encode()).hexdigest()[:12]


def matches(m, e):
    """Does the match `m` (one of key/class/title) select the entry dict `e` (as in entries.json)?"""
    k, v = next(iter(m.items()))
    if k == "title":
        return v.lower() in e.get("title", "").lower()
    return e.get(k) == v


def rule_for(ov, e):
    """The first entry rule that matches, or {}."""
    return next((r for r in ov["entries"] if matches(r["match"], e)), {})


def sort_order(ov, items):
    """Entries (dicts) reordered by ov['order'] (listed ones first, in that order; the rest keep their relative order after)."""
    rank = []
    for e in items:
        r = next((i for i, m in enumerate(ov["order"]) if matches(m, e)), None)
        rank.append(len(ov["order"]) if r is None else r)
    return [e for _, _, e in sorted(zip(rank, range(len(items)), items), key=lambda t: (t[0], t[1]))]
