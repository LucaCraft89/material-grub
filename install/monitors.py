#!/usr/bin/env python3
"""Find the primary monitor's resolution (best effort, never fatal). stdlib only.
Order: X11 xrandr primary -> Wayland (GNOME/Mutter gdbus, KDE kscreen-doctor, wlr-randr) -> DRM sysfs (internal panel first, else the largest
connected output) -> GRUB_GFXMODE from /etc/default/grub -> 1920x1080. Desktop tools run as $SUDO_USER with that user's session environment.
usage: monitors.py [--json | --best]      Each candidate: {"name", "w", "h", "primary", "source"}"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def parse_xrandr(text):
    """`xrandr --query`: connected outputs with their current mode (the one marked *, else the preferred +); primary flag from the header line."""
    out, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^(\S+) connected( primary)?\s*(\d+)x(\d+)\+\d+\+\d+", line)
        m2 = re.match(r"^(\S+) connected( primary)?\b", line)
        if m2:
            cur = {"name": m2[1], "w": 0, "h": 0, "primary": bool(m2[2]), "source": "xrandr", "_pref": None}
            out.append(cur)
            if m:
                cur["w"], cur["h"] = int(m[3]), int(m[4])
        elif re.match(r"^\S", line):
            cur = None
        elif cur:
            mm = re.match(r"^\s+(\d+)x(\d+)\S*\s+(.*)$", line)
            if mm:
                if "*" in mm[3] and not cur["w"]:
                    cur["w"], cur["h"] = int(mm[1]), int(mm[2])
                if "+" in mm[3] and not cur["_pref"]:
                    cur["_pref"] = (int(mm[1]), int(mm[2]))
    for o in out:
        pref = o.pop("_pref")
        if not o["w"] and pref:
            o["w"], o["h"] = pref
    return [o for o in out if o["w"]]


def parse_kscreen(text):
    """`kscreen-doctor -j`: enabled outputs; primary = priority 1 (Plasma 6) or primary:true (Plasma 5)."""
    try:
        data = json.loads(text)
    except ValueError:
        return []
    out = []
    for o in data.get("outputs", []):
        if not o.get("enabled", True):
            continue
        mode = next((m for m in o.get("modes", []) if m.get("id") == o.get("currentModeId")), None)
        size = (mode or {}).get("size") or o.get("size") or {}
        if size.get("width"):
            out.append(
                {
                    "name": o.get("name", "?"),
                    "w": int(size["width"]),
                    "h": int(size["height"]),
                    "primary": o.get("priority") == 1 or bool(o.get("primary")),
                    "source": "kscreen",
                }
            )
    return out


def parse_wlr_randr(text):
    """`wlr-randr`: enabled outputs and their current mode (no notion of primary: the first output is reported as primary)."""
    out, cur = [], None
    for line in text.splitlines():
        if re.match(r"^\S", line):
            cur = {"name": line.split()[0], "w": 0, "h": 0, "primary": False, "source": "wlr-randr", "_on": True}
            out.append(cur)
        elif cur and re.match(r"^\s+Enabled:\s*no", line):
            cur["_on"] = False
        elif cur:
            m = re.match(r"^\s+(\d+)x(\d+) px.*\bcurrent\b", line)
            if m:
                cur["w"], cur["h"] = int(m[1]), int(m[2])
    out = [o for o in out if o.pop("_on") and o["w"]]
    if out:
        out[0]["primary"] = True
    return out


def parse_mutter(text):
    """`gdbus call ... org.gnome.Mutter.DisplayConfig GetCurrentState` (GVariant text): the current mode of each monitor; primary from the logical monitor flag.
    Best effort: the GVariant text is parsed with regexes, not a real parser."""
    out = []
    # monitors: (('DP-1', 'vendor', 'product', 'serial'), [ ('2560x1440@59.9', 2560, 1440, 59.9, 1.0, [1.0], {'is-current': <true>, ...}), ... ], {props})
    heads = list(re.finditer(r"\(\('([^']+)',[^)]*\),\s*\[", text))
    for i, h in enumerate(heads):
        block = text[h.end() : heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        cm = re.search(r"\('[^']*',\s*(\d+),\s*(\d+),[^()]*?\[[^\]]*\],\s*\{[^}]*'is-current':\s*<true>", block)
        if cm:
            out.append({"name": h[1], "w": int(cm[1]), "h": int(cm[2]), "primary": False, "source": "mutter"})
    pm = re.search(r"\(-?\d+,\s*-?\d+,\s*[\d.]+,\s*uint32 \d+,\s*true,\s*\[\('([^']+)'", text)
    for o in out:
        o["primary"] = bool(pm) and o["name"] == pm[1]
    if out and not any(o["primary"] for o in out):
        out[0]["primary"] = True
    return out


def parse_drm(root="/sys/class/drm"):
    """Connected DRM connectors with their first (preferred) mode. Internal panels (eDP/LVDS/DSI) are marked primary; else the largest output."""
    out = []
    for st in sorted(Path(root).glob("card*-*/status")):
        try:
            if st.read_text().strip() != "connected":
                continue
            m = re.match(r"(\d+)x(\d+)", (st.parent / "modes").read_text().splitlines()[0])
        except (OSError, IndexError):
            continue
        if m:
            out.append(
                {
                    "name": st.parent.name.split("-", 1)[1],
                    "w": int(m[1]),
                    "h": int(m[2]),
                    "primary": False,
                    "source": "drm",
                }
            )
    internal = [o for o in out if re.match(r"(eDP|LVDS|DSI)", o["name"])]
    pick = internal[0] if internal else max(out, key=lambda o: o["w"] * o["h"], default=None)
    if pick:
        pick["primary"] = True
    return out


def grub_gfxmode(path="/etc/default/grub"):
    try:
        m = re.search(r"^GRUB_GFXMODE=\"?(\d{3,5})x(\d{3,5})", Path(path).read_text(), re.M)
    except OSError:
        return None
    return {"name": "GRUB_GFXMODE", "w": int(m[1]), "h": int(m[2]), "primary": False, "source": "grub"} if m else None


def _user_env():
    """Session environment of the invoking user when running under sudo (None when not root or no sudo user)."""
    user = os.environ.get("SUDO_USER")
    if os.geteuid() != 0 or not user or user == "root":
        return None
    try:
        import pwd

        pw = pwd.getpwnam(user)
    except (KeyError, ImportError):
        return None
    run = f"/run/user/{pw.pw_uid}"
    env = {
        "DISPLAY": os.environ.get("DISPLAY", ":0"),
        "XDG_RUNTIME_DIR": run,
        "DBUS_SESSION_BUS_ADDRESS": f"unix:path={run}/bus",
        "WAYLAND_DISPLAY": next(
            (p.name for p in sorted(Path(run).glob("wayland-*")) if not p.name.endswith(".lock")), "wayland-0"
        ),
    }
    xa = os.environ.get("XAUTHORITY") or next(
        (
            str(p)
            for p in (
                Path(pw.pw_dir) / ".Xauthority",
                *Path(run).glob("gdm/Xauthority"),
                *Path(run).glob(".mutter-Xwaylandauth.*"),
            )
            if p.exists()
        ),
        None,
    )
    if xa:
        env["XAUTHORITY"] = xa
    return user, env


def _run(cmd):
    if not shutil.which(cmd[0]):
        return ""
    ue = _user_env()
    try:
        if ue:
            cmd = ["runuser", "-u", ue[0], "--", "env", *[f"{k}={v}" for k, v in ue[1].items()], *cmd]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=8).stdout
    except Exception:
        return ""


def detect(drm_root="/sys/class/drm", grub="/etc/default/grub"):
    """Candidates, best first: the primary monitor (flagged), then the other connected ones, then GRUB_GFXMODE, then the 1920x1080 default."""
    found = []
    for fn, cmd in (
        (parse_xrandr, ["xrandr", "--query"]),
        (parse_kscreen, ["kscreen-doctor", "-j"]),
        (
            parse_mutter,
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                "org.gnome.Mutter.DisplayConfig",
                "--object-path",
                "/org/gnome/Mutter/DisplayConfig",
                "--method",
                "org.gnome.Mutter.DisplayConfig.GetCurrentState",
            ],
        ),
        (parse_wlr_randr, ["wlr-randr"]),
    ):
        found = fn(_run(cmd))
        if found:
            break
    found = found or parse_drm(drm_root)
    found.sort(key=lambda o: not o["primary"])
    seen, res = set(), []
    for o in found:
        if (o["w"], o["h"]) not in seen:
            seen.add((o["w"], o["h"]))
            res.append(o)
    g = grub_gfxmode(grub)
    if g and (g["w"], g["h"]) not in seen:
        res.append(g)
        seen.add((g["w"], g["h"]))
    if not res:
        res.append({"name": "default", "w": 1920, "h": 1080, "primary": False, "source": "default"})
    return res


if __name__ == "__main__":
    c = detect()
    if "--best" in sys.argv:
        print(f"{c[0]['w']}x{c[0]['h']}")
    else:
        print(json.dumps(c, indent=1))
