"""Boot a prepared ESP/boot tree in QEMU. usage: qemu_tree.py TREE WxH [keys...]  (TREE gets EFI/BOOT/BOOTX64.EFI added)"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tree, res, keys = Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
(tree / "NvVars").unlink(missing_ok=True)  # stale firmware vars change boot behaviour
(tree / "EFI/BOOT").mkdir(parents=True, exist_ok=True)
mods = "normal configfile gfxterm gfxmenu png all_video efi_gop video video_fb fat part_gpt part_msdos font echo test true search reboot halt terminal gettext blscfg regexp sleep videoinfo"


def have_module(name):
    """Debian and Ubuntu's GRUB has no blscfg.mod (Fedora's has): leave out what this GRUB cannot link in. Unknown module directory: keep everything."""
    for d in (
        "/usr/lib/grub/x86_64-efi",
        "/usr/lib64/grub/x86_64-efi",
        "/usr/share/grub2/x86_64-efi",
        "/usr/lib/grub2/x86_64-efi",
    ):
        if os.path.isdir(d):
            return os.path.exists(f"{d}/{name}.mod")
    return True


if os.environ.get("MG_QEMU_GOP_ONLY") == "1":
    # What a real UEFI machine has: only the firmware's GOP modes. `all_video` also pulls in the Bochs/Cirrus drivers, which find QEMU's VGA and then
    # accept ANY mode (1280x721 included): a test of "the firmware does not offer this mode" needs them out of the image.
    mods = mods.replace(" all_video", "").replace("efi_gop", "efi_gop efi_uga")
mods = " ".join(m for m in mods.split() if have_module(m))
subprocess.run(
    [
        shutil.which("grub2-mkimage") or shutil.which("grub-mkimage") or "grub2-mkimage",
        "-O",
        "x86_64-efi",
        "-o",
        str(tree / "EFI/BOOT/BOOTX64.EFI"),
        "-p",
        "/boot/grub",
    ]
    + mods.split(),
    check=True,
)


def find_ovmf():
    cands = [
        os.environ.get("OVMF_CODE", ""),
        "/usr/share/edk2/ovmf/OVMF_CODE.fd",
        "/usr/share/OVMF/OVMF_CODE.fd",
        "/usr/share/OVMF/OVMF_CODE_4M.fd",
        "/usr/share/edk2/x64/OVMF_CODE.4m.fd",
        "/usr/share/edk2/x64/OVMF_CODE.fd",
        "/usr/share/edk2-ovmf/x64/OVMF_CODE.fd",
        "/usr/share/qemu/OVMF.fd",
    ]
    hit = next((c for c in cands if c and os.path.exists(c)), None)
    if not hit:
        sys.exit("OVMF firmware not found; install it (edk2-ovmf / ovmf) or set OVMF_CODE=/path/to/OVMF_CODE.fd")
    return hit


KVM = os.access(
    "/dev/kvm", os.W_OK
)  # CI runners without KVM fall back to (slow) software emulation: raise BOOT_WAIT there
sock = (
    Path(tempfile.mkdtemp(prefix="mgq-")) / "mon.sock"
)  # a short path: a unix socket path is limited to about 100 characters
sock.unlink(missing_ok=True)
w, h = res.split("x")
q = subprocess.Popen(
    [
        "qemu-system-x86_64",
        "-machine",
        "q35",
        *(["-enable-kvm", "-cpu", "host"] if KVM else ["-cpu", "max"]),
        "-m",
        "1024",
        "-display",
        "none",
        "-vga",
        "none",
        "-device",
        f"VGA,vgamem_mb=64,xres={w},yres={h}",
        "-drive",
        f"if=pflash,format=raw,readonly=on,file={find_ovmf()}",
        "-drive",
        f"format=raw,file=fat:rw:{tree}",
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
            time.sleep(float(os.environ.get("KEY_WAIT", "1.8")))
        out = ROOT / f"build/tree-{i}.ppm"
        mon(f"screendump {out}")
        time.sleep(0.5)
        from PIL import Image

        Image.open(out).convert("RGB").save(ROOT / f"build/tree-{i}.png")
        print("shot", i)
finally:
    q.terminate()
