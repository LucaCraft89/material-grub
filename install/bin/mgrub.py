"""Shared helpers for material-grub tools (stdlib only)."""

import json
import re
import sys
from pathlib import Path

import mgcore  # noqa: F401  (puts material-boot-core, the shared code, on sys.path)
from material_boot.catalog import GENERIC  # noqa: F401  (catalog aliases too generic to match an entry by themselves)
from material_boot.conf import (  # noqa: F401  (/etc/material-grub.conf)
    CONF_CHOICES,
    CONF_DEFAULTS,
    _conf_ok,
    load_conf,
    write_conf,
)
from material_boot.titles import key_for, kind_of, load_rules, parse_title, uid  # noqa: F401  (which distro a title is)

HERE = Path(__file__).resolve().parent

# The one list of built-in resolutions (install/bin/resolutions.json); the packager, the installer, the TUI and the README check read it.
RESOLUTIONS = json.loads((HERE / "resolutions.json").read_text())["resolutions"]


def snap(res, available=None):
    """The resolution to build for `res`: exact size, else the closest aspect ratio, then the closest height."""
    avail = list(available or RESOLUTIONS)
    w, h = map(int, res.split("x"))
    if res in avail:
        return res

    def size(r):
        return tuple(map(int, r.split("x")))

    return min(avail, key=lambda r: (abs(size(r)[0] / size(r)[1] - w / h) > 0.02, abs(size(r)[1] - h)))


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
