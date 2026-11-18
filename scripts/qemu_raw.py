"""Boot a raw grub.cfg (+ optional BLS entries) in QEMU, send keys, screenshot. usage: qemu_raw.py CFG BLS_DIR|- [keys...]"""

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
cfg, bls, keys = Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
ESP = ROOT / "build/esp-raw"
shutil.rmtree(ESP, ignore_errors=True)
(ESP / "EFI/BOOT").mkdir(parents=True)
(ESP / "boot/grub").mkdir(parents=True)
mods = "normal configfile gfxterm gfxmenu png all_video efi_gop video video_fb fat part_gpt part_msdos font echo test true search reboot halt terminal gettext blscfg regexp"
subprocess.run(
    [
        shutil.which("grub2-mkimage") or shutil.which("grub-mkimage") or "grub2-mkimage",
        "-O",
        "x86_64-efi",
        "-o",
        str(ESP / "EFI/BOOT/BOOTX64.EFI"),
        "-p",
        "/boot/grub",
    ]
    + mods.split(),
    check=True,
)
shutil.copy(cfg, ESP / "boot/grub/grub.cfg")
if bls != "-":
    if (Path(bls) / "entries").is_dir():
        shutil.copytree(Path(bls), ESP / "loader")
    else:
        shutil.copytree(bls, ESP / "loader/entries")
sock = ROOT / "build/mon.sock"
sock.unlink(missing_ok=True)
q = subprocess.Popen(
    [
        "qemu-system-x86_64",
        "-machine",
        "q35",
        "-enable-kvm",
        "-cpu",
        "host",
        "-m",
        "1024",
        "-display",
        "none",
        "-vga",
        "none",
        "-device",
        "VGA,vgamem_mb=64,xres=1920,yres=1200",
        "-drive",
        "if=pflash,format=raw,readonly=on,file=/usr/share/edk2/ovmf/OVMF_CODE.fd",
        "-drive",
        f"format=raw,file=fat:rw:{ESP}",
        "-monitor",
        f"unix:{sock},server,nowait",
    ],
    stderr=subprocess.DEVNULL,
)


def mon(c):
    s = socket.socket(socket.AF_UNIX)
    s.connect(str(sock))
    s.settimeout(2)
    time.sleep(0.2)
    try:
        s.recv(4096)
    except Exception:
        pass
    s.sendall((c + "\n").encode())
    time.sleep(0.6)
    s.close()


try:
    time.sleep(float(os.environ.get("BOOT_WAIT", "12")))
    for i, k in enumerate(["-"] + keys):
        if k != "-":
            mon("sendkey " + k)
            time.sleep(float(os.environ.get("KEY_WAIT", "1.2")))
        out = ROOT / f"build/raw-{i}.ppm"
        mon(f"screendump {out}")
        time.sleep(0.5)
        subprocess.run(["magick", str(out), str(ROOT / f"build/raw-{i}.png")], check=True)
        print("shot", i)
finally:
    q.terminate()
