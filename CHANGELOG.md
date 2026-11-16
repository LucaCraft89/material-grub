# Changelog

## 0.1.0 (2026-11-16)

First public release.

- Per-entry full-screen scenes with Material 3 Expressive dark palettes derived from each distro's brand colour (54 catalog entries: 48 distros, Windows 10/11, Firmware, Restart, Shut down, Tux fallback).
- Info pills (kernel version, OS version, edition, default, rescue mode), a Linux | Windows | System section rail, and the raw entry title at the bottom of the screen.
- Fedora BLS entries: default kernel on top, everything else (including rescue) under **Advanced options** with gear / wrench icons.
- Firmware (BGRT) logo drawn live in a cookie shape at the top right.
- Resolutions: 1280x720, 1920x1080, 1920x1200, 2560x1080, 2560x1440, 3440x1440, 3840x2160 (16:9, 16:10, 21:9).
- One-command installer (`sudo ./install.sh`): detects the distro, installs only missing dependencies, shows live progress, backs up GRUB files, supports `--uninstall`.
- Bundles Google Sans Flex v5.000 (SIL OFL 1.1) unmodified, with upstream's licence and trademark notice.

Known limitations: no animation, no wavy progress bar, countdown/raw-name colours are neutral (GRUB themes are static); the GRUB-rewriting step is verified on Fedora 44 only.
