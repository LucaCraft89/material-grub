#!/usr/bin/env python3
"""Boot a Ventoy stick in QEMU + OVMF with the theme installed, change the ISOs WITHOUT running the installer again, and check what Ventoy draws.
Needs: qemu-system-x86_64, OVMF, mtools (mformat/mcopy/mdel), Pillow, a built package (dist/material-grub, 1920x1080, dark) and network access once
(downloads Ventoy 1.1.18 into build/ventoy-cache, sha256 checked). No root: the stick is an image file filled with mtools.
usage: python3 tests/ventoy_smoke.py [PKG_DIR]"""
import hashlib, json, lzma, os, shutil, socket, struct, subprocess, sys, tarfile, tempfile, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; PKG = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "dist/material-grub")
VER = "1.1.18"; SHA = "d86ff9de63d94c8b8f1f6b14d23c55af4b88e8207bf2893890892a6a97b1ad54"
URL = f"https://github.com/ventoy/Ventoy/releases/download/v{VER}/ventoy-{VER}-linux.tar.gz"; CACHE = ROOT / "build/ventoy-cache"
OVMF = next((c for c in ("/usr/share/edk2/ovmf/OVMF_CODE.fd", "/usr/share/OVMF/OVMF_CODE.fd", "/usr/share/OVMF/OVMF_CODE_4M.fd", "/usr/share/edk2/x64/OVMF_CODE.4m.fd", "/usr/share/qemu/OVMF.fd") if os.path.exists(c)), None)
MIB = 1 << 20

def fetch():
    """efi.img (Ventoy's 32 MiB boot partition) and boot.img (its MBR boot code)."""
    CACHE.mkdir(parents=True, exist_ok=True); tgz = CACHE / f"ventoy-{VER}-linux.tar.gz"
    if not tgz.exists() or hashlib.sha256(tgz.read_bytes()).hexdigest() != SHA:
        urllib.request.urlretrieve(URL, tgz)
        if hashlib.sha256(tgz.read_bytes()).hexdigest() != SHA: tgz.unlink(); sys.exit("Ventoy download: checksum mismatch")
    if not (CACHE / "efi.img").exists():
        with tarfile.open(tgz) as t:
            (CACHE / "efi.img").write_bytes(lzma.decompress(t.extractfile(f"./ventoy-{VER}/ventoy/ventoy.disk.img.xz").read()))
            (CACHE / "boot.img").write_bytes(t.extractfile(f"./ventoy-{VER}/boot/boot.img").read())
    return CACHE / "efi.img", CACHE / "boot.img"

def make_stick(path, total_mib=520):
    """MBR disk like Ventoy2Disk makes: data partition (FAT32) from 1 MiB, then the 32 MiB boot partition (type EF, active) at the end."""
    efi, boot = fetch(); p2 = total_mib - 33; p1_sectors = (p2 - 1) * MIB // 512; p2_sectors = 32 * MIB // 512
    mbr = bytearray(boot.read_bytes()[:446])
    ent = lambda status, typ, start, size: struct.pack("<B3sB3sII", status, b"\xfe\xff\xff", typ, b"\xfe\xff\xff", start, size)
    mbr += ent(0, 0x0C, 2048, p1_sectors) + ent(0x80, 0xEF, p2 * MIB // 512, p2_sectors) + bytes(32) + b"\x55\xaa"
    with open(path, "wb") as f: f.truncate(total_mib * MIB)
    with open(path, "r+b") as f: f.write(mbr); f.seek(p2 * MIB); f.write(efi.read_bytes())
    subprocess.run(["mformat", "-i", f"{path}@@1M", "-F", "-v", "Ventoy", "::"], check=True)

def mt(img, *a): subprocess.run([a[0], "-i", f"{img}@@1M", *a[1:]], check=True, capture_output=True)

def boot(img, shots, res=(1920, 1080), wait=22):
    """Boot the image, press down between screenshots; returns the list of PIL images."""
    from PIL import Image
    tmp = Path(tempfile.mkdtemp()); sock = str(tmp / "mon.sock")
    kvm = os.access("/dev/kvm", os.W_OK)
    q = subprocess.Popen(["qemu-system-x86_64", "-machine", "q35", *(["-enable-kvm", "-cpu", "host"] if kvm else ["-cpu", "max"]), "-m", "2048", "-display", "none", "-vga", "none",
                          "-device", f"VGA,vgamem_mb=64,xres={res[0]},yres={res[1]}", "-drive", f"if=pflash,format=raw,readonly=on,file={OVMF}",
                          "-drive", f"format=raw,file={img},snapshot=on", "-monitor", f"unix:{sock},server,nowait"], stderr=subprocess.DEVNULL)
    def mon(c):
        s = socket.socket(socket.AF_UNIX)
        for _ in range(50):
            try: s.connect(sock); break
            except OSError: time.sleep(.1)
        s.settimeout(2); time.sleep(.2)
        try: s.recv(4096)
        except Exception: pass
        s.sendall((c + "\n").encode()); time.sleep(.6); s.close()
    out = []
    try:
        time.sleep(wait * (1 if kvm else 4))
        for i in range(shots):
            if i: mon("sendkey down"); time.sleep(2 if kvm else 6)
            mon(f"screendump {tmp}/s{i}.ppm"); time.sleep(.5); out.append(Image.open(tmp / f"s{i}.ppm").convert("RGB"))
    finally: q.terminate(); shutil.rmtree(tmp, ignore_errors=True)
    return out

def ventoy_hashes(img):
    """sha1 of every file under /ventoy inside the stick image (to prove nothing was rewritten between the two boots)."""
    d = Path(tempfile.mkdtemp()); subprocess.run(["mcopy", "-s", "-i", f"{img}@@1M", "::/ventoy", str(d)], check=True, capture_output=True)
    h = {str(p.relative_to(d)): hashlib.sha1(p.read_bytes()).hexdigest() for p in d.rglob("*") if p.is_file()}; shutil.rmtree(d, ignore_errors=True); return h

def near(a, b, tol=10): return all(abs(x - y) <= tol for x, y in zip(a, b))
hexc = lambda c: tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))

def check(name, img, key, pal):
    """The dynamic list draws the selected distro's glyph in a cookie of its primaryContainer colour at (25% of the width, 450); sample inside it, away from the glyph."""
    W, H = img.size; px = img.getpixel((round(W * .25) - round(160 * H / 1080), round(450 * H / 1080))); want = hexc(pal[key]["primaryContainer"])
    ok = near(px, want); print(f"  {'ok  ' if ok else 'FAIL'} {name}: cookie colour {px} vs {key} {want}"); return ok

if __name__ == "__main__":
    for tool in ("qemu-system-x86_64", "mformat", "mcopy", "mdel"):
        if not shutil.which(tool): sys.exit(f"skipped: {tool} not found")
    if not OVMF: sys.exit("skipped: OVMF firmware not found")
    if not (PKG / "res/1920x1080").is_dir(): sys.exit(f"skipped: no 1920x1080 package at {PKG}")
    pal = json.loads((PKG / "palettes.json").read_text()); work = Path(tempfile.mkdtemp()); stage = work / "stage"; (stage / "ventoy").mkdir(parents=True); (stage / "ISO").mkdir()
    for n in ("Fedora-Workstation-Live-x86_64-44-1.7.iso", "ubuntu-24.04.1-desktop-amd64.iso"): (stage / "ISO" / n).write_bytes(b"\0" * MIB)
    r = subprocess.run(["sh", str(ROOT / "install.sh"), "--ventoy", str(stage), "--pkg", str(PKG), "--res", "1920x1080", "--style", "list", "--scheme", "dark", "--yes", "--no-tui"], capture_output=True, text=True)
    if r.returncode: sys.exit("installer failed:\n" + r.stdout + r.stderr)
    img = work / "stick.img"; make_stick(img); subprocess.run(["mcopy", "-s", "-i", f"{img}@@1M", *map(str, stage.iterdir()), "::/"], check=True)
    before = ventoy_hashes(img)
    ok = True
    print("1. installed with two ISOs (Fedora, Ubuntu)")
    a = boot(img, 2); ok &= check("first entry (Fedora)", a[0], "fedora", pal); ok &= check("second entry (Ubuntu)", a[1], "ubuntu", pal)
    print("2. now, WITHOUT running anything: add Arch, Linux Mint, Win11 and an unrecognised image; rename Ubuntu (capital U); remove Fedora")
    for n in ("archlinux-2026.11.01-x86_64.iso", "linuxmint-22-cinnamon-64bit.iso", "Win11_24H2_English_x64.iso", "Ubuntu-Desktop-26.04-amd64.iso", "gparted-live-1.6.0-1-amd64.iso"):
        f = work / n; f.write_bytes(b"\0" * MIB); mt(img, "mcopy", str(f), f"::/ISO/{n}")
    mt(img, "mdel", "::/ISO/Fedora-Workstation-Live-x86_64-44-1.7.iso"); mt(img, "mdel", "::/ISO/ubuntu-24.04.1-desktop-amd64.iso")
    b = boot(img, 5)       # sorted: archlinux, gparted, linuxmint, Ubuntu-Desktop, Win11
    for i, (n, k) in enumerate((("archlinux", "arch"), ("gparted (unrecognised: grey disc)", "iso"), ("linuxmint", "linuxmint"), ("Ubuntu-Desktop (renamed)", "ubuntu"), ("Win11", "windows11"))): ok &= check(n, b[i], k, pal)
    print("3. the theme files were not touched in between")
    same = ventoy_hashes(img) == before and len(before) > 100; print(f"  {'ok  ' if same else 'FAIL'} all {len(before)} files under /ventoy identical before and after"); ok &= same
    shutil.rmtree(work, ignore_errors=True); print("PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)
