# Tested on

Systems where somebody installed the theme and looked at the real menu. Add yours with the
[Works on my distro](https://github.com/LucaCraft89/material-grub/issues/new?template=works_on_distro.yml) form; this table is updated from those reports.

| Distribution | GRUB | Firmware | Resolution | Style | Installed | Kernel update | Uninstall | Reported |
|---|---|---|---|---|---|---|---|---|
| Fedora 44 Workstation (BLS) | 2.12 | UEFI | 1920x1200 | split, dark | yes | yes | yes | maintainer, 2026-11 |

Automatically tested in CI on every pull request (containers, not real hardware): the installer on Fedora, Ubuntu, Debian, Arch, openSUSE, Alpine and
AlmaLinux 8; `--dry-run` on Debian and Fedora; the boot of every style and the safety nets in QEMU/OVMF; Ventoy 1.1.18 in QEMU.
