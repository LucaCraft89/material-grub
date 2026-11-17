"""Shared helpers for material-grub tools (stdlib only)."""
import json, re
from pathlib import Path

def load_rules(pkg): return json.loads((Path(pkg) / "rules.json").read_text())

def key_for(title, rules):
    """Match an entry title (case-insensitive, token based) to a catalog key; None if unknown/Windows."""
    toks = re.findall(r"[a-z0-9]+", title.lower())
    if "windows" in toks or "microsoft" in toks: return None
    for r in rules:
        t = r["tokens"]; n = len(t)
        if any(toks[i:i + n] == t for i in range(len(toks) - n + 1)): return r["key"]
        if "".join(t) in toks: return r["key"]
    return None

import hashlib

def uid(*parts): return "mg_" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]

def parse_title(title):
    """Extract kernel/os/edition info from BLS or classic GRUB entry titles."""
    t = title.strip(); d = {"os": None, "kver": None, "osver": None, "edition": None, "where": None}
    m = re.search(r"\(on (/dev/[^)\s]+)\)", t)
    if m: d["where"] = m.group(1); t = t.replace(m.group(0), "").strip()
    m = re.match(r"^(?P<os>.+?) (?P<v>\d\S*) \((?P<ed>[^)]+)\) \((?P<k>ostree:\d+)\)$", t)                  # ostree: Fedora Linux 44.20260301.0 (Silverblue) (ostree:0)
    if m: d.update(os=m["os"], osver=m["v"], edition=m["ed"], kver=m["k"]); return d
    m = re.match(r"^(?P<os>.+?) \((?P<kver>[^)]+)\) (?P<osver>\S+)(?: \((?P<ed>[^)]+)\))?$", t)   # BLS: Fedora Linux (6.x) 44 (Workstation)
    if m: d.update(os=m["os"], kver=m["kver"], osver=m["osver"], edition=m["ed"]); return d
    m = re.match(r"^(?P<os>.+?), with (?P<k>[A-Za-z]+) (?P<v>\S+)(?: \((?P<x>[^)]+)\))?$", t)        # classic: Ubuntu, with Linux 6.8.0-45-generic (recovery mode)
    if m: d.update(os=m["os"], kver=m["v"], edition=m["x"]); return d
    m = re.match(r"^(?P<os>[A-Za-z][A-Za-z!_ /\-]*?)\s+(?P<v>\d[\w.\-+ ]*)$", t)                        # os-prober: Ubuntu 24.04.1 LTS
    if m: d.update(os=m["os"], osver=m["v"]); return d
    d["os"] = t; return d

def kind_of(title, key, is_submenu=False):
    if is_submenu and re.search(r"advanced options", title, re.I): return "advanced"
    if re.search(r"recovery|rescue", title, re.I): return "rescue"
    if key in ("windows10", "windows11", "firmware", "reboot", "shutdown"): return "plain"
    return "kernel"


CONF_DEFAULTS = {"RAW_NAME": "on", "COUNTDOWN": "on", "LOGO": "on", "TIMEOUT": ""}
def load_conf(path=None):
    """/etc/material-grub.conf: KEY=value lines, '#' comments. Unknown keys and bad values are ignored (never fatal in a boot-config path)."""
    import os
    c = dict(CONF_DEFAULTS); path = path or os.environ.get("MATERIAL_CONF", "/etc/material-grub.conf")
    try:
        for line in Path(path).read_text().splitlines():
            m = re.match(r"^\s*([A-Z_]+)\s*=\s*\"?([^\"#]*?)\"?\s*(?:#.*)?$", line)
            if not m or m[1] not in c: continue
            k, v = m[1], m[2].strip()
            if k == "TIMEOUT": c[k] = v if v.isdigit() else ""
            elif v.lower() in ("on", "off", "yes", "no", "true", "false", "1", "0"): c[k] = "on" if v.lower() in ("on", "yes", "true", "1") else "off"
    except OSError: pass
    return c

def apply_conf_to_theme(text, conf):
    """Drop the '# mg:begin NAME' .. '# mg:end NAME' blocks of theme.txt that the config switches off."""
    for key, name in (("RAW_NAME", "raw"), ("COUNTDOWN", "countdown"), ("LOGO", "logo")):
        if conf[key] == "off": text = re.sub(rf"(?ms)^# mg:begin {name}\n.*?^# mg:end {name}\n", "", text)
    return text


# `blscfg` is how GRUB loads BootLoaderSpec entries. Distros call it as a bare line (Fedora), indented inside an if, or with options.
_BLS = re.compile(r"^(?P<ind>\s*)blscfg(?P<args>(?:\s+[^#;|&]*?)?)\s*(?:#.*)?$")
def bls_call(line):
    """None if the line is not a blscfg call. Else (indent, args). Only a bare call or --enable-fallback can be restructured:
    options that pick the directory or filter entries (--path, --show-default, --show-non-default) would fight our mirrors."""
    m = _BLS.match(line)
    return (m["ind"], m["args"].strip()) if m else None
def bls_restructurable(call):
    return call is not None and call[1] in ("", "--enable-fallback")
