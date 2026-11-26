#!/usr/bin/env python3
"""Build the bundle: one tarball with the core and the parts, and an installer that installs any of them (docs/installer.md).

  python3 scripts/build_bundle.py --out DIR [--config bundle.json] [--part NAME=CHECKOUT]... [--release] [--epoch SECONDS]

  --out DIR            writes DIR/material-boot-<version>.tar.gz and DIR/material-boot-<version>.tar.gz.sha256 (and leaves the unpacked tree next to them)
  --config FILE        which parts, from where, pinned (default: bundle.json next to this repository's VERSION)
  --part NAME=PATH     use this git checkout for the part NAME instead of fetching `repo` at `ref` (development, tests); its committed files are taken
  --release            every `ref` must be a tag (v1.2.3): a release is never built from a branch
  --epoch SECONDS      the time put in the archive (default: $SOURCE_DATE_EPOCH, else this repository's last commit): the same inputs give the same bytes

A part's repository keeps its manifest in `material-boot-part.json` at its root (plugin API 2, docs/plugins.md; `entry` relative to the repository).
The build refuses a part whose manifest is not usable, so a bundle never holds a part that the installer would then refuse.

The tree: install.sh, VERSION, BUNDLE.json (what is in it, from where, at which commit), SHA256SUMS, lib/material_boot, bin/material-boot, scripts/build_data.py,
assets/, parts/<name>/ (the part's repository, with its manifest also as manifest.json).
"""

import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from material_boot import CORE_API, __version__, plugins  # noqa: E402

TAG = re.compile(r"^v\d+\.\d+\.\d+$")
PART_MANIFEST = "material-boot-part.json"


def run(*cmd, cwd=None):
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True)
    if r.returncode:
        raise SystemExit(f"{' '.join(map(str, cmd))} failed: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout


def export(checkout, dest):
    """The committed files of a git checkout (not what is untracked or ignored there) into `dest`, and its commit."""
    commit = run("git", "-C", checkout, "rev-parse", "HEAD").decode().strip()
    tar = run("git", "-C", checkout, "archive", "--format=tar", "HEAD")
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        t.extractall(dest, filter="data") if hasattr(tarfile, "data_filter") else t.extractall(dest)
    return commit


def fetch(repo, ref, dest, work):
    """A part at `ref` from GitHub (a shallow clone), exported like a local checkout."""
    clone = work / repo.replace("/", "_")
    run("git", "clone", "--quiet", "--depth", "1", "--branch", ref, f"https://github.com/{repo}", clone)
    return export(clone, dest)


def copy_core(stage):
    ign = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(ROOT / "material_boot", stage / "lib/material_boot", ignore=ign)
    (stage / "lib/material_boot/VERSION").write_text(__version__ + "\n")
    (stage / "scripts").mkdir()
    shutil.copy(ROOT / "scripts/build_data.py", stage / "scripts/build_data.py")
    shutil.copytree(ROOT / "assets", stage / "assets")
    (stage / "bin").mkdir()
    shutil.copy(ROOT / "bin/material-boot", stage / "bin/material-boot")
    for f in ("LICENSE", "THIRD_PARTY.md", "VERSION"):
        shutil.copy(ROOT / f, stage / f)
    shutil.copy(ROOT / "packaging/bundle/install.sh", stage / "install.sh")
    os.chmod(stage / "install.sh", 0o755)
    os.chmod(stage / "bin/material-boot", 0o755)


def add_part(stage, name, spec, local, release, work):
    """Put one part in parts/<name>/ and check its manifest. Returns what BUNDLE.json says about it."""
    ref = spec.get("ref", "")
    if release and not TAG.match(ref):
        raise SystemExit(
            f"--release: the part '{name}' is pinned to '{ref}', which is not a tag (v1.2.3): a release is never built from a branch"
        )
    dest = stage / "parts" / name
    commit = export(local[name], dest) if name in local else fetch(spec["repo"], ref, dest, work)
    src = dest / PART_MANIFEST
    if not src.is_file():
        raise SystemExit(f"the part '{name}' has no {PART_MANIFEST} at the root of its repository")
    shutil.copyfile(src, dest / "manifest.json")
    rec = plugins.read_manifest(dest / "manifest.json")
    if rec.problem:
        raise SystemExit(f"the part '{name}' cannot be used: {rec.problem}")
    if rec.name != name:
        raise SystemExit(f"bundle.json calls the part '{name}' but its manifest says '{rec.name}'")
    return {
        "repo": spec.get("repo"),
        "ref": ref if name not in local else f"{ref} (local checkout)",
        "commit": commit,
        "version": rec.version,
    }


def checksums(stage):
    lines = []
    for p in sorted(stage.rglob("*")):
        if p.is_file() and p.name != "SHA256SUMS":
            lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(stage).as_posix()}")
    (stage / "SHA256SUMS").write_text("\n".join(lines) + "\n")


def tarball(stage, out, epoch):
    """A reproducible archive: sorted, owner 0, one fixed time, gzip without a time stamp."""
    name = stage.name
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as t:
        for p in sorted([stage, *stage.rglob("*")], key=lambda x: x.relative_to(stage.parent).as_posix()):
            ti = t.gettarinfo(str(p), arcname=p.relative_to(stage.parent).as_posix())
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = ""
            ti.mtime = epoch
            ti.mode = 0o755 if (p.is_dir() or os.access(p, os.X_OK)) else 0o644
            if p.is_file():
                with open(p, "rb") as f:
                    t.addfile(ti, f)
            else:
                t.addfile(ti)
    gz = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=gz, mtime=0, compresslevel=9) as g:
        g.write(raw.getvalue())
    dest = out / f"{name}.tar.gz"
    dest.write_bytes(gz.getvalue())
    (out / f"{name}.tar.gz.sha256").write_text(f"{hashlib.sha256(gz.getvalue()).hexdigest()}  {dest.name}\n")
    return dest


def default_epoch():
    if os.environ.get("SOURCE_DATE_EPOCH"):
        return int(os.environ["SOURCE_DATE_EPOCH"])
    try:
        return int(run("git", "-C", ROOT, "log", "-1", "--format=%ct").decode().strip())
    except SystemExit:
        return int(time.time())


def build(out, config, local, release=False, epoch=None):
    out = Path(out)
    cfg = json.loads(Path(config).read_text())
    if cfg.get("format") != 1:
        raise SystemExit(f"{config}: unknown format {cfg.get('format')!r}")
    stage = out / f"material-boot-{__version__}"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    copy_core(stage)
    parts = {}
    with tempfile.TemporaryDirectory(prefix="bundle-") as work:
        for name in sorted(cfg["parts"]):
            parts[name] = add_part(stage, name, cfg["parts"][name], local, release, Path(work))
    (stage / "BUNDLE.json").write_text(
        json.dumps({"core": __version__, "plugin_api": CORE_API, "parts": parts}, indent=1, sort_keys=True) + "\n"
    )
    checksums(stage)
    return tarball(stage, out, default_epoch() if epoch is None else epoch), stage


def main(argv):
    def many(n):
        return [argv[i + 1] for i, a in enumerate(argv) if a == n and i + 1 < len(argv)]

    out = (many("--out") or [None])[0]
    if not out:
        raise SystemExit(__doc__)
    config = (many("--config") or [str(ROOT / "bundle.json")])[0]
    local = {}
    for spec in many("--part"):
        name, _, path = spec.partition("=")
        if not path:
            raise SystemExit(f"--part wants NAME=PATH, not {spec!r}")
        local[name] = path
    epoch = int(many("--epoch")[0]) if many("--epoch") else None
    tar, stage = build(out, config, local, "--release" in argv, epoch)
    print(f"bundle: {tar} ({tar.stat().st_size} bytes)\ntree:   {stage}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
