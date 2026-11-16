"""Boot the theme in QEMU+OVMF and screenshot. usage: qemu_test.py THEME_DIR WxH  [keys...]"""
import os, shutil, socket, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
theme, res = Path(sys.argv[1]).resolve(), sys.argv[2]; keys = sys.argv[3:] or ["down"]
ESP = ROOT / "build/esp"; shutil.rmtree(ESP, ignore_errors=True)
(ESP / "EFI/BOOT").mkdir(parents=True); (ESP / "boot/grub/themes").mkdir(parents=True)
mods = "normal configfile gfxterm gfxmenu png all_video efi_gop video video_fb fat part_gpt part_msdos font echo test true search reboot halt terminal gettext"
subprocess.run(["grub2-mkimage", "-O", "x86_64-efi", "-o", str(ESP / "EFI/BOOT/BOOTX64.EFI"), "-p", "/boot/grub"] + mods.split(), check=True)
shutil.copytree(theme, ESP / "boot/grub/themes/material")
entries = [("Fedora Linux", "fedora gnu-linux gnu os"), ("Windows Boot Manager", "windows os"), ("Arch Linux", "arch gnu-linux gnu os"),
           ("Ubuntu", "ubuntu gnu-linux gnu os"), ("Debian GNU/Linux", "debian gnu-linux gnu os"), ("Some Other Linux", "gnu-linux gnu os"),
           ("UEFI Firmware Settings", "efi"), ("Reboot", "restart"), ("Shutdown", "shutdown")]
if os.environ.get("SAMPLE"):
    entries = [("Zorin OS", "zorin gnu-linux"), ("Bazzite", "bazzite"), ("Windows Boot Manager", "windows os"),
               ("CachyOS", "cachyos"), ("Mystery Distro", "mystery gnu-linux gnu os"), ("Pop!_OS", "pop_os gnu-linux")]
cfg = f"""set timeout={os.environ.get('TMO', '30')}
set gfxmode={res}
set gfxpayload=keep
insmod all_video
insmod gfxterm
insmod gfxmenu
insmod png
loadfont /boot/grub/themes/material/GSF-Label.pf2
terminal_output gfxterm
set theme=/boot/grub/themes/material/theme.txt
""" + "".join(f"menuentry '{t}' --class {c.replace(' ', ' --class ')} {{ true }}\n" for t, c in entries)
(ESP / "boot/grub/grub.cfg").write_text(cfg)
sock = ROOT / "build/mon.sock"; sock.unlink(missing_ok=True)
q = subprocess.Popen(["qemu-system-x86_64", "-machine", "q35", "-m", "1024", "-display", "none", "-vga", "none", "-device", f"VGA,vgamem_mb=64,xres={res.split('x')[0]},yres={res.split('x')[1]}",
    "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/edk2/ovmf/OVMF_CODE.fd",
    "-drive", f"format=raw,file=fat:rw:{ESP}", "-monitor", f"unix:{sock},server,nowait"], stderr=subprocess.DEVNULL)
def mon(cmd):
    s = socket.socket(socket.AF_UNIX); s.connect(str(sock)); s.settimeout(2); time.sleep(.2)
    try: s.recv(4096)
    except Exception: pass
    s.sendall((cmd + "\n").encode()); time.sleep(.6); s.close()
try:
    time.sleep(float(os.environ.get("BOOT_WAIT", "12")))
    for i, k in enumerate(["-"] + keys):
        if k != "-": mon("sendkey " + k); time.sleep(float(os.environ.get("KEY_WAIT", "1.5")))
        out = ROOT / f"build/qemu-{i}.ppm"; mon(f"screendump {out}"); time.sleep(.5)
        subprocess.run(["magick", str(out), str(ROOT / f"build/qemu-{i}.png")], check=True)
        print("shot", ROOT / f"build/qemu-{i}.png")
finally:
    q.terminate()
