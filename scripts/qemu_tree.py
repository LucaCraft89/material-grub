"""Boot a prepared ESP/boot tree in QEMU. usage: qemu_tree.py TREE WxH [keys...]  (TREE gets EFI/BOOT/BOOTX64.EFI added)"""
import os, shutil, socket, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
tree, res, keys = Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
(tree / "NvVars").unlink(missing_ok=True)   # stale firmware vars change boot behaviour
(tree / "EFI/BOOT").mkdir(parents=True, exist_ok=True)
mods = "normal configfile gfxterm gfxmenu png all_video efi_gop video video_fb fat part_gpt part_msdos font echo test true search reboot halt terminal gettext blscfg regexp"
subprocess.run([shutil.which("grub2-mkimage") or shutil.which("grub-mkimage") or "grub2-mkimage", "-O", "x86_64-efi", "-o", str(tree / "EFI/BOOT/BOOTX64.EFI"), "-p", "/boot/grub"] + mods.split(), check=True)
sock = ROOT / "build/mon.sock"; sock.unlink(missing_ok=True); w, h = res.split("x")
q = subprocess.Popen(["qemu-system-x86_64", "-machine", "q35", "-enable-kvm", "-cpu", "host", "-m", "1024", "-display", "none", "-vga", "none",
    "-device", f"VGA,vgamem_mb=64,xres={w},yres={h}", "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/edk2/ovmf/OVMF_CODE.fd",
    "-drive", f"format=raw,file=fat:rw:{tree}", "-monitor", f"unix:{sock},server,nowait"], stderr=subprocess.DEVNULL)
def mon(c):
    s = socket.socket(socket.AF_UNIX); s.connect(str(sock)); s.settimeout(2); time.sleep(.2)
    try: s.recv(4096)
    except Exception: pass
    s.sendall((c + "\n").encode()); time.sleep(.6); s.close()
try:
    time.sleep(float(os.environ.get("BOOT_WAIT", "12")))
    for i, k in enumerate(["-"] + keys):
        if k != "-": mon("sendkey " + k); time.sleep(float(os.environ.get("KEY_WAIT", "1.8")))
        out = ROOT / f"build/tree-{i}.ppm"; mon(f"screendump {out}"); time.sleep(.5)
        subprocess.run(["magick", str(out), str(ROOT / f"build/tree-{i}.png")], check=True); print("shot", i)
finally: q.terminate()
