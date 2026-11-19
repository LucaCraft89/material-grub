"""Shared helpers for material-grub tools (stdlib only)."""

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# The one list of built-in resolutions (install/bin/resolutions.json); the packager, the installer, the TUI and the README check read it.
RESOLUTIONS = json.loads((HERE / "resolutions.json").read_text())["resolutions"]

# Catalog aliases that are too generic to match an entry by themselves (shared by the packager, the Ventoy tool and the distro table).
GENERIC = {"os", "gnu", "gnu-linux", "unknown", "win", "mx", "nix", "linux"}


def snap(res, available=None):
    """The resolution to build for `res`: exact size, else the closest aspect ratio, then the closest height."""
    avail = list(available or RESOLUTIONS)
    w, h = map(int, res.split("x"))
    if res in avail:
        return res

    def size(r):
        return tuple(map(int, r.split("x")))

    return min(avail, key=lambda r: (abs(size(r)[0] / size(r)[1] - w / h) > 0.02, abs(size(r)[1] - h)))


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


CONF_DEFAULTS = {
    "RAW_NAME": "on",
    "COUNTDOWN": "on",
    "LOGO": "on",
    "COOKIE": "on",
    "HINTS": "on",
    "STYLE": "rail",
    "SCHEME": "dark",
    "TIMEOUT": "",
    "MODE": "dynamic",
    # the optional Plymouth part (material-plymouth) reads these; they do nothing while it is not installed
    "PLYMOUTH": "on",
    "PLYMOUTH_BAR": "indeterminate",
    "PLYMOUTH_MOTION": "full",
}
CONF_CHOICES = {
    "STYLE": ("rail", "clean", "list", "split", "full"),
    "SCHEME": ("dark", "light"),
    "MODE": ("dynamic", "snapshot"),
    "PLYMOUTH_BAR": ("indeterminate", "progress"),
    "PLYMOUTH_MOTION": ("full", "calm", "off"),
}


def load_conf(path=None):
    """/etc/material-grub.conf: KEY=value lines, '#' comments. Unknown keys and bad values are ignored (never fatal in a boot-config path)."""
    import os

    c = dict(CONF_DEFAULTS)
    path = path or os.environ.get("MATERIAL_CONF", "/etc/material-grub.conf")
    try:
        for line in Path(path).read_text().splitlines():
            m = re.match(r"^\s*([A-Z_]+)\s*=\s*\"?([^\"#]*?)\"?\s*(?:#.*)?$", line)
            if not m or m[1] not in c:
                continue
            k, v = m[1], m[2].strip()
            if k == "TIMEOUT":
                c[k] = v if v.isdigit() else ""
            elif k in CONF_CHOICES:
                c[k] = v.lower() if v.lower() in CONF_CHOICES[k] else c[k]
            elif v.lower() in ("on", "off", "yes", "no", "true", "false", "1", "0"):
                c[k] = "on" if v.lower() in ("on", "yes", "true", "1") else "off"
    except OSError:
        pass
    return c


def _conf_ok(key, value):
    """Strict check for write_conf (load_conf is lenient on purpose; a writer must not store junk)."""
    if key not in CONF_DEFAULTS:
        return False
    if key == "TIMEOUT":
        return value == "" or value.isdigit()
    if key in CONF_CHOICES:
        return value in CONF_CHOICES[key]
    return value in ("on", "off")


def write_conf(path, updates):
    """Set KEY=value in the conf file, atomically (temp file in the same directory, then rename).
    Replaces the first active or commented-out sample line of a key (keeps the comments), else appends.
    Raises ValueError for an unknown key or a bad value, before anything is written."""
    import os
    import tempfile

    for k, v in updates.items():
        if not _conf_ok(k, str(v)):
            raise ValueError(f"bad config: {k}={v!r}")
    path = Path(path)
    try:
        lines = path.read_text().splitlines()
        mode = path.stat().st_mode & 0o7777
    except OSError:
        lines, mode = [], 0o644
    for k, v in updates.items():
        new = f"{k}={v}"
        active = re.compile(rf"^\s*{k}\s*=")
        sample = re.compile(rf"^#\s*{k}\s*=")
        for rx in (active, sample):
            hit = next((i for i, ln in enumerate(lines) if rx.match(ln)), None)
            if hit is not None:
                lines[hit] = new
                break
        else:
            lines.append(new)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".mgconf.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.chmod(tmp, mode)
        os.replace(tmp, str(path))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def apply_conf_to_theme(text, conf):
    """Drop the '# mg:begin NAME' .. '# mg:end NAME' blocks of theme.txt that the config switches off (no cookie also means no logo in it)."""
    for key, name in (("RAW_NAME", "raw"), ("COUNTDOWN", "countdown"), ("LOGO", "logo")):
        if conf[key] == "off" or (name == "logo" and conf["COOKIE"] == "off"):
            text = re.sub(rf"(?ms)^# mg:begin {name}\n.*?^# mg:end {name}\n", "", text)
    if conf.get("STYLE") == "clean":
        text = _clean_layout(text)
    if conf.get("STYLE") in ("list", "split"):
        text = _list_layout(text)
    return text


def _list_layout(text):
    """`list` centres the menu on the screen, so the countdown moves down between the list and the key hints (1080-high design: info chips 846-892, bar 896, label 912, key hints from 960)."""
    m = re.search(r"(?ms)^# mg:begin countdown\n(.*?)^# mg:end countdown\n", text)
    if not m:
        return text
    body = m[1]
    lab = re.search(r"label \{.*?\n\}", body, re.S)
    hh = re.search(r"^\s*height = (\d+)$", lab[0], re.M) if lab else None
    if not (lab and hh):
        return text
    f = int(hh[1]) / 34

    def settop(chunk, v):
        return re.sub(r"^(\s*top = )-?\d+$", rf"\g<1>{v}", chunk, count=1, flags=re.M)

    parts = body.split("+ label {")
    parts[0] = settop(parts[0], round(896 * f))
    parts[1] = settop(parts[1], round(912 * f))
    return text[: m.start(1)] + "+ label {".join(parts) + text[m.end(1) :]


def _clean_layout(text):
    """`clean` draws its panel inside a 24 px margin and 96 px top bar, so the BGRT logo moves with the cookie (design values scaled by the bundle's own factor, recovered from the logo width).
    The raw-name line stays at the very bottom: GRUB shows as many rows as fit between its top and the screen edge, which is what keeps it a 1-item list."""

    def block(name, fn):
        return re.sub(
            rf"(?ms)^(# mg:begin {name}\n)(.*?)(^# mg:end {name}\n)", lambda m: m[1] + fn(m[2]) + m[3], text, count=1
        )

    def num(body, k):
        m = re.search(rf"^\s*{k} = (-?\d+)$", body, re.M)
        return int(m[1]) if m else None

    def setnum(body, k, v):
        return re.sub(rf"^(\s*{k} = )-?\d+$", rf"\g<1>{v}", body, count=1, flags=re.M)

    def logo(b):
        w, l, t = num(b, "width"), num(b, "left"), num(b, "top")
        if None in (w, l, t):
            return b
        f = w / 120
        return setnum(setnum(b, "left", l - round(24 * f)), "top", t + round(96 * f))

    return block("logo", logo)


# `blscfg` is how GRUB loads BootLoaderSpec entries. Distros call it as a bare line (Fedora), indented inside an if, or with options.
_BLS = re.compile(r"^(?P<ind>\s*)blscfg(?P<args>(?:\s+[^#;|&]*?)?)\s*(?:#.*)?$")


def bls_call(line):
    """None if the line is not a blscfg call. Else (indent, args). Only a bare call or --enable-fallback can be restructured:
    options that pick the directory or filter entries (--path, --show-default, --show-non-default) would fight our mirrors."""
    m = _BLS.match(line)
    return (m["ind"], m["args"].strip()) if m else None


def bls_restructurable(call):
    return call is not None and call[1] in ("", "--enable-fallback")


if __name__ == "__main__":  # used by install.sh: `mgrub.py list` / `mgrub.py snap WxH[,WxH...]`
    if sys.argv[1:2] == ["list"]:
        print(" ".join(RESOLUTIONS))
    elif sys.argv[1:2] == ["snap"] and len(sys.argv) == 3:
        out = []
        for r in sys.argv[2].split(","):
            try:
                s = snap(r)
            except ValueError:
                sys.exit(f"mgrub: bad resolution {r!r} (expected WxH)")
            if s not in out:
                out.append(s)
        print(",".join(out))
    else:
        sys.exit("usage: mgrub.py list | snap WxH[,WxH...]")
