"""The settings file shared by every part: /etc/material-grub.conf (`KEY=value` lines, `#` comments; $MATERIAL_CONF moves it). stdlib only.

Moved verbatim from material-grub's mgrub.py (release/0.8.0, 588f909); tests/test_provenance.py checks that. The theme's keys (STYLE, SCHEME, COOKIE, LOGO, ...)
and the parts' keys (PLYMOUTH, PLYMOUTH_BAR, PLYMOUTH_MOTION) live in the same file on purpose: the look is shared by every part. A part's manifest names
the keys it owns (docs/plugins.md); the defaults and the allowed values are still here, in one place, until a part can bring its own.
"""

import re
from pathlib import Path

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
