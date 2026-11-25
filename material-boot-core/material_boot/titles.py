"""Boot entries: which distro a title is, and what kind of entry it is. stdlib only.

Moved verbatim from material-grub's mgrub.py (release/0.8.0, 588f909); tests/test_provenance.py checks that. material-plymouth uses `load_rules`,
`key_for` and `parse_title` to say which distro is booting; material-grub uses all of it on the titles in grub.cfg.
"""

import hashlib
import json
import re
from pathlib import Path


def load_rules(pkg):
    return json.loads((Path(pkg) / "rules.json").read_text())


def key_for(title, rules):
    """Match an entry title (case-insensitive, token based) to a catalog key; None if unknown/Windows."""
    toks = re.findall(r"[a-z0-9]+", title.lower())
    if "windows" in toks or "microsoft" in toks:
        return None
    for r in rules:
        t = r["tokens"]
        n = len(t)
        if any(toks[i : i + n] == t for i in range(len(toks) - n + 1)):
            return r["key"]
        if "".join(t) in toks:
            return r["key"]
    return None


def uid(*parts):
    return "mg_" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]


def parse_title(title):
    """Extract kernel/os/edition info from BLS or classic GRUB entry titles."""
    t = title.strip()
    d = {"os": None, "kver": None, "osver": None, "edition": None, "where": None}
    m = re.search(r"\(on (/dev/[^)\s]+)\)", t)
    if m:
        d["where"] = m.group(1)
        t = t.replace(m.group(0), "").strip()
    m = re.match(
        r"^(?P<os>.+?) (?P<v>\d\S*) \((?P<ed>[^)]+)\) \((?P<k>ostree:\d+)\)$", t
    )  # ostree: Fedora Linux 44.20260301.0 (Silverblue) (ostree:0)
    if m:
        d.update(os=m["os"], osver=m["v"], edition=m["ed"], kver=m["k"])
        return d
    m = re.match(
        r"^(?P<os>.+?) \((?P<kver>[^)]+)\) (?P<osver>\S+)(?: \((?P<ed>[^)]+)\))?$", t
    )  # BLS: Fedora Linux (6.x) 44 (Workstation)
    if m:
        d.update(os=m["os"], kver=m["kver"], osver=m["osver"], edition=m["ed"])
        return d
    m = re.match(
        r"^(?P<os>.+?), with (?P<k>[A-Za-z]+) (?P<v>\S+)(?: \((?P<x>[^)]+)\))?$", t
    )  # classic: Ubuntu, with Linux 6.8.0-45-generic (recovery mode)
    if m:
        d.update(os=m["os"], kver=m["v"], edition=m["x"])
        return d
    m = re.match(r"^(?P<os>[A-Za-z][A-Za-z!_ /\-]*?)\s+(?P<v>\d[\w.\-+ ]*)$", t)  # os-prober: Ubuntu 24.04.1 LTS
    if m:
        d.update(os=m["os"], osver=m["v"])
        return d
    d["os"] = t
    return d


def kind_of(title, key, is_submenu=False):
    if is_submenu and re.search(r"advanced options", title, re.I):
        return "advanced"
    if re.search(r"recovery|rescue", title, re.I):
        return "rescue"
    if key in ("windows10", "windows11", "firmware", "reboot", "shutdown"):
        return "plain"
    return "kernel"
