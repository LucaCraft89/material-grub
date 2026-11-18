#!/usr/bin/env python3
"""Screenshots of the Ventoy theme: real Ventoy 1.1.18 in QEMU + OVMF, a stick filled with tiny real ISOs (genisoimage), the theme installed by install.sh --ventoy.
Needs: dist/material-grub (scripts/package.py; its scheme decides dark or light), qemu-system-x86_64, OVMF, mtools, genisoimage, Pillow, network once (Ventoy download, see tests/ventoy_smoke.py).
usage: scripts/make_ventoy_screenshots.py [--extras]  -> docs/screenshots/ventoy/<style>-<scheme>-<n>.png (two per style); --extras also writes the F5 tools menu, the F3 tree view and the boot-mode menu (dark only)"""

import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import ventoy_smoke as V
from PIL import Image

PKG = ROOT / "dist/material-grub"
OUT = ROOT / "docs/screenshots/ventoy"
ISOS = [
    "archlinux-2026.11.01-x86_64.iso",
    "debian-live-13.1.0-amd64-gnome.iso",
    "Fedora-Workstation-Live-x86_64-44-1.7.iso",
    "linuxmint-22-cinnamon-64bit.iso",
    "pnlug_zilla_f.iso",
    "ubuntu-24.04.1-desktop-amd64.iso",
    "Win11_24H2_English_x64.iso",
]  # Ventoy lists them in this order


def make_isos(d):
    src = d / "iso"
    (src / "sources").mkdir(parents=True)
    (src / "sources/boot.wim").write_bytes(b"x" * 4096)
    (src / "README").write_text("material-grub screenshot image")
    out = d / "ISO"
    out.mkdir()
    for n in ISOS:
        subprocess.run(["genisoimage", "-quiet", "-o", str(out / n), "-V", "TEST", str(src)], check=True)
    return out


def session(style, scheme, keys, d):
    """Install `style` on a fresh stick, boot it, send `keys` one by one; returns a screenshot before the first key and after each key."""
    n = len(list(d.glob("stage-*")))
    stage = d / f"stage-{n}"
    (stage / "ventoy").mkdir(parents=True)
    shutil.copytree(d / "ISO", stage / "ISO")
    r = subprocess.run(
        [
            "sh",
            str(ROOT / "install.sh"),
            "--ventoy",
            str(stage),
            "--pkg",
            str(PKG),
            "--res",
            "1920x1080",
            "--style",
            style,
            "--scheme",
            scheme,
            "--yes",
            "--no-tui",
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode:
        sys.exit(r.stdout + r.stderr)
    img = d / f"stick-{n}.img"
    V.make_stick(img, 700)
    subprocess.run(["mcopy", "-s", "-i", f"{img}@@1M", *map(str, stage.iterdir()), "::/"], check=True)
    sock = str(d / f"mon-{n}.sock")
    q = subprocess.Popen(
        [
            "qemu-system-x86_64",
            "-machine",
            "q35",
            "-enable-kvm",
            "-cpu",
            "host",
            "-m",
            "2048",
            "-display",
            "none",
            "-vga",
            "none",
            "-device",
            "VGA,vgamem_mb=64,xres=1920,yres=1080",
            "-drive",
            f"if=pflash,format=raw,readonly=on,file={V.OVMF}",
            "-drive",
            f"format=raw,file={img},snapshot=on",
            "-monitor",
            f"unix:{sock},server,nowait",
        ],
        stderr=subprocess.DEVNULL,
    )

    def mon(c):
        s = socket.socket(socket.AF_UNIX)
        for _ in range(50):
            try:
                s.connect(sock)
                break
            except OSError:
                time.sleep(0.1)
        s.settimeout(2)
        time.sleep(0.2)
        try:
            s.recv(4096)
        except Exception:
            pass
        s.sendall((c + "\n").encode())
        time.sleep(0.6)
        s.close()

    shots = []
    try:
        time.sleep(22)
        for i, k in enumerate(["-"] + keys):
            if k != "-":
                mon("sendkey " + k)
                time.sleep(3)
            mon(f"screendump {d}/s{n}-{i}.ppm")
            time.sleep(0.5)
            shots.append(Image.open(d / f"s{n}-{i}.ppm").convert("RGB"))
    finally:
        q.terminate()
    return shots


if __name__ == "__main__":
    for tool in ("qemu-system-x86_64", "mformat", "mcopy", "genisoimage"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found")
    scheme = (PKG / "scheme.txt").read_text().strip()
    OUT.mkdir(parents=True, exist_ok=True)
    d = Path(tempfile.mkdtemp())
    make_isos(d)
    for style in ("full", "list"):
        # keys: down x2 -> Fedora, down x2 more -> PNLug
        s = session(style, scheme, ["down", "down", "down", "down"], d)
        s[2].save(OUT / f"{style}-{scheme}-1.png", optimize=True)
        s[4].save(OUT / f"{style}-{scheme}-2.png", optimize=True)
        print("wrote", style, scheme)
        if "--extras" in sys.argv and style == "list":
            e = session("list", scheme, ["f5", "esc", "f3"], d)
            e[1].save(OUT / "tools-menu.png", optimize=True)
            e[3].save(OUT / "tree-view.png", optimize=True)
            print("wrote tools-menu, tree-view")
        if "--extras" in sys.argv and style == "full":
            e = session("full", scheme, ["down", "down", "ret"], d)
            e[3].save(OUT / "full-boot-modes.png", optimize=True)
            print("wrote full-boot-modes")
    shutil.rmtree(d, ignore_errors=True)
