#!/usr/bin/env python3
"""Compare the data build with a package material-grub built (dist/material-grub): every shared file must be byte for byte the same.

python3 scripts/compare_data.py BUILT_DIR MATERIAL_GRUB_PACKAGE_DIR
"""

import sys
from pathlib import Path

SHARED = ("palettes.json", "classes.json", "rules.json", "titles.json", "subtitles.json", "scheme.txt")


def main(built, pkg):
    built, pkg = Path(built), Path(pkg)
    files = [Path(f) for f in SHARED] + sorted(
        p.relative_to(built) for p in built.rglob("*") if p.is_file() and p.parent != built
    )
    bad, n = [], 0
    for f in dict.fromkeys(files):
        a, b = built / f, pkg / f
        n += 1
        if not a.is_file() or not b.is_file():
            bad.append(f"{f}: missing in {'the build' if not a.is_file() else 'the package'}")
        elif a.read_bytes() != b.read_bytes():
            bad.append(f"{f}: differs")
    extra = sorted(
        str(p.relative_to(pkg))
        for d in ("glyphs", "fonts")
        for p in (pkg / d).rglob("*")
        if p.is_file() and not (built / p.relative_to(pkg)).is_file()
    )
    bad += [f"{f}: only in the package" for f in extra]
    if bad:
        print(f"{len(bad)} differences in {n} files:\n  " + "\n  ".join(bad[:20]))
        return 1
    print(f"identical: {n} files")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]) if len(sys.argv) >= 3 else print(__doc__))
