# Gallery

Real GRUB output captured in QEMU + OVMF (`make screenshots`), and a rendered sample of every supported distro. Back to the [README](../README.md); Ventoy screenshots are in [ventoy.md](ventoy.md).

## Styles and schemes

<table>
<tr>
<td><img src="screenshots/advanced.png" alt="Advanced options entry with gear icon"></td>
<td><img src="screenshots/rescue.png" alt="Rescue entry with wrench icon"></td>
</tr>
<tr>
<td><img src="screenshots/windows.png" alt="Windows 11 entry"></td>
<td><img src="screenshots/arch.png" alt="Arch Linux entry"></td>
</tr>
<tr>
<td><img src="screenshots/ubuntu.png" alt="Ubuntu entry"></td>
<td><img src="screenshots/firmware.png" alt="UEFI Firmware Settings entry"></td>
</tr>
</table>

Light scheme (`sudo ./install.sh --scheme light`):

<table>
<tr>
<td><img src="screenshots/light-fedora.png" alt="Fedora entry, light scheme"></td>
<td><img src="screenshots/light-windows.png" alt="Windows 11 entry, light scheme"></td>
</tr>
<tr>
<td><img src="screenshots/light-arch.png" alt="Arch Linux entry, light scheme"></td>
<td><img src="screenshots/light-ubuntu.png" alt="Ubuntu entry, light scheme"></td>
</tr>
</table>

<img src="screenshots/light-ultrawide-fedora.png" alt="Ultrawide 21:9 layout, light scheme" width="100%">

Ultrawide (2560×1080):

<img src="screenshots/ultrawide-fedora.png" alt="Ultrawide 21:9 layout" width="100%">

<sub>All screenshots are real GRUB output, captured in QEMU + OVMF with `make screenshots`. The Dell logo is this author's firmware logo.</sub>

## Supported distros

Entries are matched by name and GRUB class; each distro gets its own colour, logo and name. The samples below are rendered from the theme code and kept in sync by CI.

<!-- distros:begin -->
<p>All 54 supported distros and system entries, rendered from the theme code:</p>

<table>
<tr><td align="center"><img src="distros/fedora.png" width="200" alt="Fedora"><br><sub>Fedora</sub></td><td align="center"><img src="distros/nobara.png" width="200" alt="Nobara"><br><sub>Nobara</sub></td><td align="center"><img src="distros/bazzite.png" width="200" alt="Bazzite"><br><sub>Bazzite</sub></td><td align="center"><img src="distros/ubuntu.png" width="200" alt="Ubuntu"><br><sub>Ubuntu</sub></td></tr>
<tr><td align="center"><img src="distros/kubuntu.png" width="200" alt="Kubuntu"><br><sub>Kubuntu</sub></td><td align="center"><img src="distros/debian.png" width="200" alt="Debian"><br><sub>Debian</sub></td><td align="center"><img src="distros/devuan.png" width="200" alt="Devuan"><br><sub>Devuan</sub></td><td align="center"><img src="distros/kali.png" width="200" alt="Kali Linux"><br><sub>Kali Linux</sub></td></tr>
<tr><td align="center"><img src="distros/parrot.png" width="200" alt="Parrot OS"><br><sub>Parrot OS</sub></td><td align="center"><img src="distros/tails.png" width="200" alt="Tails"><br><sub>Tails</sub></td><td align="center"><img src="distros/mxlinux.png" width="200" alt="MX Linux"><br><sub>MX Linux</sub></td><td align="center"><img src="distros/deepin.png" width="200" alt="Deepin"><br><sub>Deepin</sub></td></tr>
<tr><td align="center"><img src="distros/zorin.png" width="200" alt="Zorin OS"><br><sub>Zorin OS</sub></td><td align="center"><img src="distros/linuxmint.png" width="200" alt="Linux Mint"><br><sub>Linux Mint</sub></td><td align="center"><img src="distros/elementary.png" width="200" alt="elementary OS"><br><sub>elementary OS</sub></td><td align="center"><img src="distros/pop.png" width="200" alt="Pop!_OS"><br><sub>Pop!_OS</sub></td></tr>
<tr><td align="center"><img src="distros/arch.png" width="200" alt="Arch Linux"><br><sub>Arch Linux</sub></td><td align="center"><img src="distros/endeavouros.png" width="200" alt="EndeavourOS"><br><sub>EndeavourOS</sub></td><td align="center"><img src="distros/manjaro.png" width="200" alt="Manjaro"><br><sub>Manjaro</sub></td><td align="center"><img src="distros/garuda.png" width="200" alt="Garuda Linux"><br><sub>Garuda Linux</sub></td></tr>
<tr><td align="center"><img src="distros/artix.png" width="200" alt="Artix Linux"><br><sub>Artix Linux</sub></td><td align="center"><img src="distros/arcolinux.png" width="200" alt="ArcoLinux"><br><sub>ArcoLinux</sub></td><td align="center"><img src="distros/archcraft.png" width="200" alt="Archcraft"><br><sub>Archcraft</sub></td><td align="center"><img src="distros/cachyos.png" width="200" alt="CachyOS"><br><sub>CachyOS</sub></td></tr>
<tr><td align="center"><img src="distros/biglinux.png" width="200" alt="BigLinux"><br><sub>BigLinux</sub></td><td align="center"><img src="distros/opensuse.png" width="200" alt="openSUSE"><br><sub>openSUSE</sub></td><td align="center"><img src="distros/nixos.png" width="200" alt="NixOS"><br><sub>NixOS</sub></td><td align="center"><img src="distros/gentoo.png" width="200" alt="Gentoo"><br><sub>Gentoo</sub></td></tr>
<tr><td align="center"><img src="distros/void.png" width="200" alt="Void Linux"><br><sub>Void Linux</sub></td><td align="center"><img src="distros/alpine.png" width="200" alt="Alpine"><br><sub>Alpine</sub></td><td align="center"><img src="distros/slackware.png" width="200" alt="Slackware"><br><sub>Slackware</sub></td><td align="center"><img src="distros/solus.png" width="200" alt="Solus"><br><sub>Solus</sub></td></tr>
<tr><td align="center"><img src="distros/mageia.png" width="200" alt="Mageia"><br><sub>Mageia</sub></td><td align="center"><img src="distros/puppy.png" width="200" alt="Puppy Linux"><br><sub>Puppy Linux</sub></td><td align="center"><img src="distros/vanilla.png" width="200" alt="Vanilla OS"><br><sub>Vanilla OS</sub></td><td align="center"><img src="distros/sabayon.png" width="200" alt="Sabayon"><br><sub>Sabayon</sub></td></tr>
<tr><td align="center"><img src="distros/openwrt.png" width="200" alt="OpenWrt"><br><sub>OpenWrt</sub></td><td align="center"><img src="distros/postmarketos.png" width="200" alt="postmarketOS"><br><sub>postmarketOS</sub></td><td align="center"><img src="distros/qubes.png" width="200" alt="Qubes OS"><br><sub>Qubes OS</sub></td><td align="center"><img src="distros/neon.png" width="200" alt="KDE neon"><br><sub>KDE neon</sub></td></tr>
<tr><td align="center"><img src="distros/rocky.png" width="200" alt="Rocky Linux"><br><sub>Rocky Linux</sub></td><td align="center"><img src="distros/almalinux.png" width="200" alt="AlmaLinux"><br><sub>AlmaLinux</sub></td><td align="center"><img src="distros/centos.png" width="200" alt="CentOS"><br><sub>CentOS</sub></td><td align="center"><img src="distros/rhel.png" width="200" alt="Red Hat"><br><sub>Red Hat</sub></td></tr>
<tr><td align="center"><img src="distros/freebsd.png" width="200" alt="FreeBSD"><br><sub>FreeBSD</sub></td><td align="center"><img src="distros/openbsd.png" width="200" alt="OpenBSD"><br><sub>OpenBSD</sub></td><td align="center"><img src="distros/guix.png" width="200" alt="GNU Guix"><br><sub>GNU Guix</sub></td><td align="center"><img src="distros/raspberrypi.png" width="200" alt="Raspberry Pi OS"><br><sub>Raspberry Pi OS</sub></td></tr>
<tr><td align="center"><img src="distros/tux.png" width="200" alt="Linux"><br><sub>Linux</sub></td><td align="center"><img src="distros/windows11.png" width="200" alt="Windows 11"><br><sub>Windows 11</sub></td><td align="center"><img src="distros/windows10.png" width="200" alt="Windows 10"><br><sub>Windows 10</sub></td><td align="center"><img src="distros/firmware.png" width="200" alt="Firmware"><br><sub>Firmware</sub></td></tr>
<tr><td align="center"><img src="distros/reboot.png" width="200" alt="Restart"><br><sub>Restart</sub></td><td align="center"><img src="distros/shutdown.png" width="200" alt="Shut down"><br><sub>Shut down</sub></td></tr>
</table>

Full table with the matched names: [distros.md](distros.md). Not listed? [Request your distro](https://github.com/LucaCraft89/material-grub/issues/new?template=distro_request.yml).

<!-- distros:end -->

