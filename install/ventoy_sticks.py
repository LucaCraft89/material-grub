#!/usr/bin/env python3
"""Find Ventoy sticks (best effort, never fatal). stdlib only.
A Ventoy disk has a data partition (label usually "Ventoy") and a 32 MB partition labelled VTOYEFI; the data partition is the other one on the same disk.
Mounted sticks are found through lsblk and, as a fallback, by looking for a /ventoy folder on removable mounts (/run/media, /media, /mnt).
usage: ventoy_sticks.py [--json]       Each stick: {"path": mount point or "dev:/dev/sdX1", "dev", "label", "fstype", "size", "model", "mounted"}"""
import json, os, subprocess, sys
from pathlib import Path

def parse_lsblk(text):
    """`lsblk -J -b -o NAME,PATH,LABEL,FSTYPE,SIZE,MOUNTPOINTS,MODEL,TYPE`: data partitions of disks that also have a VTOYEFI partition."""
    try: data = json.loads(text)
    except ValueError: return []
    out = []
    for disk in data.get("blockdevices", []):
        parts = disk.get("children") or []
        if not any((p.get("label") or "").upper() == "VTOYEFI" for p in parts): continue
        for p in parts:
            if (p.get("label") or "").upper() == "VTOYEFI" or p.get("type") not in (None, "part"): continue
            mps = p.get("mountpoints") if "mountpoints" in p else [p.get("mountpoint")]
            mp = next((m for m in (mps or []) if m), None)
            out.append({"path": mp or f"dev:{p.get('path') or '/dev/' + p['name']}", "dev": p.get("path") or "/dev/" + p["name"], "label": p.get("label") or "", "fstype": p.get("fstype") or "",
                        "size": int(p.get("size") or 0), "model": (disk.get("model") or "").strip(), "mounted": bool(mp), "verified": True})
    return out

def scan_mounts(roots=("/run/media", "/media", "/mnt")):
    """Fallback: any directory two levels below a removable-media root that holds a /ventoy folder."""
    out = []
    for r in roots:
        try: lvl1 = [p for p in Path(r).iterdir() if p.is_dir()]
        except OSError: continue
        for a in lvl1:
            try: cands = [a] + [p for p in a.iterdir() if p.is_dir()]
            except OSError: cands = [a]
            for c in cands:
                if (c / "ventoy").is_dir(): out.append({"path": str(c), "dev": "", "label": c.name, "fstype": "", "size": 0, "model": "", "mounted": True, "verified": False})
    return out

def detect(lsblk_text=None):
    if lsblk_text is None:
        try: lsblk_text = subprocess.run(["lsblk", "-J", "-b", "-o", "NAME,PATH,LABEL,FSTYPE,SIZE,MOUNTPOINTS,MODEL,TYPE"], capture_output=True, text=True, timeout=10).stdout
        except Exception: lsblk_text = ""
    found = parse_lsblk(lsblk_text); seen = {s["path"] for s in found}
    for s in scan_mounts():
        if s["path"] not in seen: found.append(s); seen.add(s["path"])
    # found through the VTOYEFI partition = really a Ventoy disk (a fresh one has no /ventoy folder yet); found only by scanning mounts = must hold a /ventoy folder
    return [s for s in found if s["verified"] or (Path(s["path"]) / "ventoy").is_dir()]

def sibling_vtoyefi(lsblk_list_text, dev):
    """`lsblk -J -l -o PATH,LABEL,TYPE,PKNAME` output: does the disk that holds partition `dev` also have a VTOYEFI partition?"""
    try: rows = json.loads(lsblk_list_text).get("blockdevices", [])
    except ValueError: return False
    me = next((r for r in rows if r.get("path") == dev), None)
    return bool(me and me.get("pkname") and any((r.get("label") or "").upper() == "VTOYEFI" and r.get("pkname") == me["pkname"] for r in rows))

def check(path):
    """How we know `path` is a Ventoy data partition: "partition" (its disk has a VTOYEFI partition), "folder" (it holds a /ventoy folder), or None."""
    try:
        dev = subprocess.run(["findmnt", "-n", "-o", "SOURCE", "--target", str(path)], capture_output=True, text=True, timeout=10).stdout.strip()
        text = subprocess.run(["lsblk", "-J", "-l", "-o", "PATH,LABEL,TYPE,PKNAME"], capture_output=True, text=True, timeout=10).stdout
        if dev and sibling_vtoyefi(text, dev): return "partition"
    except Exception: pass
    return "folder" if (Path(path) / "ventoy").is_dir() else None

def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1000 or unit == "TB": return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}".replace(".0 ", " ")
        n /= 1000

def describe(s):
    bits = [s["fstype"], human(s["size"]) if s["size"] else "", s["model"]]
    return f"{s['path'] if s['mounted'] else s['dev'] + ' (not mounted)'}" + (f"  [{', '.join(b for b in bits if b)}]" if any(bits) else "")

if __name__ == "__main__":
    if "--check" in sys.argv:       # --check PATH: exit 0 if PATH is a Ventoy data partition, printing how we know
        how = check(sys.argv[sys.argv.index("--check") + 1]); print(how or "not a Ventoy stick"); sys.exit(0 if how else 1)
    sticks = detect()
    if "--json" in sys.argv: print(json.dumps(sticks))
    else: print("\n".join(describe(s) for s in sticks) or "no Ventoy stick found")
