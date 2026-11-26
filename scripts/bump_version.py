#!/usr/bin/env python3
"""Set the release version everywhere it is written. stdlib only.
usage: bump_version.py X.Y.Z [--check]
Updates VERSION, material-boot-part.json, packaging/arch/PKGBUILD (pkgver, pkgrel=1), packaging/rpm/material-grub.spec (Version, Release, changelog)
and packaging/debian/debian/changelog (new entry on top). --check only reports whether they all agree with VERSION."""

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAINT = "LucaCraft89 <noreply@users.noreply.github.com>"


def read_versions():
    return {
        "VERSION": (ROOT / "VERSION").read_text().strip(),
        "PKGBUILD": re.search(r"^pkgver=(\S+)", (ROOT / "packaging/arch/PKGBUILD").read_text(), re.M).group(1),
        "spec": re.search(r"^Version:\s+(\S+)", (ROOT / "packaging/rpm/material-grub.spec").read_text(), re.M).group(1),
        "debian": re.match(
            r"material-grub \(([^)]+)\)", (ROOT / "packaging/debian/debian/changelog").read_text()
        ).group(1),
        "manifest": json.loads((ROOT / "material-boot-part.json").read_text())["version"],
    }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--check" in sys.argv:
        v = read_versions()
        print("\n".join(f"{k:9} {x}" for k, x in v.items()))
        if len(set(v.values())) != 1:
            sys.exit("the versions differ: run scripts/bump_version.py X.Y.Z")
        return
    if len(args) != 1 or not re.fullmatch(r"\d+\.\d+\.\d+", args[0]):
        sys.exit(__doc__)
    ver = args[0]
    (ROOT / "VERSION").write_text(ver + "\n")
    p = (
        ROOT / "material-boot-part.json"
    )  # the part's manifest for material-boot says the same version (tests/test_grub_part.py checks it)
    p.write_text(re.sub(r'("version":\s*)"[^"]*"', rf'\1"{ver}"', p.read_text(), count=1))
    p = ROOT / "packaging/arch/PKGBUILD"
    t = re.sub(r"^pkgver=.*$", f"pkgver={ver}", p.read_text(), flags=re.M)
    p.write_text(re.sub(r"^pkgrel=.*$", "pkgrel=1", t, flags=re.M))
    p = ROOT / "packaging/rpm/material-grub.spec"
    t = re.sub(r"^Version:.*$", f"Version:        {ver}", p.read_text(), flags=re.M)
    t = re.sub(r"^Release:.*$", "Release:        1%{?dist}", t, flags=re.M)
    day = time.strftime("%a %b %d %Y")
    if f"- {ver}-1\n" not in t:  # run twice: no second entry
        t = t.replace("%changelog\n", f"%changelog\n* {day} {MAINT} - {ver}-1\n- Release {ver}.\n\n", 1)
    p.write_text(t)
    p = ROOT / "packaging/debian/debian/changelog"
    stamp = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
    old = p.read_text()
    if not old.startswith(f"material-grub ({ver})"):
        p.write_text(
            f"material-grub ({ver}) unstable; urgency=medium\n\n  * Release {ver}.\n\n -- {MAINT}  {stamp}\n\n" + old
        )
    print(f"version set to {ver} in VERSION, the manifest, PKGBUILD, spec and debian/changelog")


if __name__ == "__main__":
    main()
