#!/usr/bin/env python3
"""Generate real GRUB screenshots (QEMU + OVMF) from the built package. Needs: dist/material-grub (scripts/package.py).
usage: make_screenshots.py [WxH ...]   (default: 1920x1080 2560x1080)  -> docs/screenshots/
       make_screenshots.py --light     (needs a package built with --scheme light) -> light-*.png"""
import shutil, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; PKG = ROOT / "dist/material-grub"; OUT = ROOT / "docs/screenshots"
BIN = PKG / "bin"; PY = sys.executable

CFG = """set timeout=120
set gfxmode={res}
set gfxpayload=keep
insmod all_video
insmod gfxterm
insmod gfxmenu
insmod png
terminal_output gfxterm
loadfont /boot/grub/themes/material/MG-Label.pf2
loadfont /boot/grub/themes/material/MG-Raw.pf2
set theme=/boot/grub/themes/material/theme.txt
insmod blscfg
blscfg
menuentry 'Windows Boot Manager (on /dev/nvme0n1p1)' --class windows --class os {{ true }}
menuentry 'Arch Linux' --class arch --class gnu-linux --class gnu --class os {{ true }}
menuentry 'Ubuntu 24.04.1 LTS (on /dev/sda5)' --class ubuntu --class gnu-linux --class gnu --class os {{ true }}
menuentry 'UEFI Firmware Settings' --class efi {{ true }}
menuentry 'Restart' --class restart --id material-reboot {{ reboot }}
menuentry 'Shut down' --class shutdown --id material-halt {{ halt }}
"""
BLS = ("Fedora Linux ({v}.fc44.x86_64) 44 (Workstation Edition)", "{v}.fc44.x86_64")

def build_tree(res, tree):
    shutil.rmtree(tree, ignore_errors=True); (tree / "loader/entries").mkdir(parents=True); (tree / "boot/grub").mkdir(parents=True)
    for v in ("7.3.3-200", "7.2.11-200", "7.2.8-200", "0-rescue-1657f3fb24ae"):
        title = BLS[0].format(v=v) if "rescue" not in v else f"Fedora Linux ({v}) 44 (Workstation Edition)"
        (tree / f"loader/entries/abc-{v.split('-')[0] + '-rescue' if 'rescue' in v else v}.conf").write_text(f"title {title}\nversion {v}\nlinux /vmlinuz-{v}\ninitrd /initramfs-{v}.img\noptions root=UUID=x ro\ngrub_class fedora\n")
    (tree / "boot/grub/grub.cfg").write_text(CFG.format(res=res))
    th = tree / "boot/grub/themes/material"; state = tree / "state/entries.json"
    subprocess.run([PY, BIN / "material-grub-assemble", "--mode", res, "--pkg", PKG, "--out", th], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([PY, BIN / "material-grub-classes", tree / "boot/grub/grub.cfg", "--pkg", PKG, "--bls", tree / "loader/entries", "--loader", tree / "loader",
                    "--blsbase", "/loader", "--state", state, "--default", "abc-7.3.3-200"], check=True)
    subprocess.run([PY, BIN / "material-grub-scenes", "--theme", th, "--state", state, "--pkg", PKG], check=True)

def shoot(res, keys, names):
    tree = ROOT / "build/shots-tree"; build_tree(res, tree)
    subprocess.run([PY, ROOT / "scripts/qemu_tree.py", tree, res] + keys, check=True, env={**__import__("os").environ, "BOOT_WAIT": "14", "KEY_WAIT": "2.2"})
    OUT.mkdir(parents=True, exist_ok=True)
    for i, n in enumerate(names):
        if n.startswith("_"): continue
        subprocess.run(["magick", ROOT / f"build/tree-{i}.png", "-strip", "-define", "png:compression-level=9", OUT / f"{n}.png"], check=True)

if __name__ == "__main__":
    resl = [a for a in sys.argv[1:] if not a.startswith("--")] or ["1920x1080", "2560x1080"]
    if "--light" in sys.argv:
        shoot("1920x1080", ["down", "down", "down", "down"], ["light-fedora", "_adv", "light-windows", "light-arch", "_ubuntu"]); sys.exit(0)
    if "1920x1080" in resl:
        # shot 0 = initial, then one per key. "_" names are navigation steps that are not kept.
        keys = ["down", "ret", "down", "down", "esc", "down", "down", "down", "down", "down", "down"]
        shoot("1920x1080", keys, ["fedora", "advanced", "kernel-older", "kernel-oldest", "rescue", "_top", "_adv", "windows", "arch", "ubuntu", "firmware", "restart"])
    if "2560x1080" in resl:
        shoot("2560x1080", ["down", "down"], ["ultrawide-fedora", "ultrawide-advanced", "ultrawide-windows"])
