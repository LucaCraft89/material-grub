# Changelog

## Unreleased (0.4 in progress)

- Phase 0, no visual change: the top-right cookie and the key-hint pills are no longer baked into the release images; `material-grub-scenes` draws them at install/apply time. New shared renderer module `install/bin/mgscenes.py` (importable, Pillow only). `/etc/material-grub.conf` gains `STYLE`, `COOKIE`, `HINTS` (and `SCHEME`, informational); `COOKIE=off` also hides the logo. `--no-hints` now writes `HINTS=off` (works with `--prebuilt` too; at package build time it is a no-op). New `install/install.sh --set KEY=value`. Checked: with the same package inputs the scenes GRUB uses are pixel-identical to v0.3 at 1920x1080 and the cookie/hints code is identical at 2x scale.
- `material-grub-classes` writes `menu.json` (entries in real menu order per menu level) and gives plain entries (Windows, Firmware, Restart, Shut down) their own unique class in addition to the shared one, so duplicates can be told apart. Installs annotated by older versions keep the old classes until grub.cfg is regenerated.
- Phase 1: `STYLE=clean` (full screen without the rail: the previous/next entry of the same menu level peek in above and below in their own colours, label chips on the panel edges, wrapping at the ends). The BGRT logo overlay moves with the cookie; plain entries get per-entry scenes. Verified in QEMU (1920x1080, dark and light, BLS Advanced submenu); other resolutions not yet.
- Phase 2: `STYLE=list` (the whole menu level is baked into each entry's scene: icon in a cookie shape plus name in a pill, gear/wrench before the name for Advanced/Rescue, selection box and background in the selected entry's palette, section dividers wherever the menu order changes group, windowing with "+N more" chips beyond about 7 rows, countdown moved below the list). Verified in QEMU at 1920x1080 (dark and light, all entries), 1920x1200, 2560x1080 and 3840x1080 (dark); 2160-high sets and real hardware not yet.
- Without Pillow the scenes now also lack the cookie and hints (before: only the rail).

## 0.3.0 (2026-11-17)

CI, non-Latin titles, a config file and prebuilt release assets.

- `blscfg` handling is now general: bare, indented, or `--enable-fallback` calls are restructured (arguments and indentation preserved); calls with directory/filter options, or inside a menu entry, are left alone with a message; systems without `blscfg` (Debian, Ubuntu, Arch: classic menuentries) are themed directly. Covered by tests.
- Prebuilt release assets: `release.yml` builds 12 resolutions x 2 schemes on a version tag and uploads them with `SHA256SUMS`; `./install.sh --prebuilt` downloads and verifies one (curl or wget, `MG_RELEASE_URL` to override). New `VERSION` file. Tested against a local server (Fedora, Alpine/busybox, tampered checksum, missing asset); the GitHub workflow has not run yet.
- Config file `/etc/material-grub.conf` (RAW_NAME, COUNTDOWN, LOGO, TIMEOUT; never overwritten), `material-grub-apply`, path unit watches it; `--no-hints` build option. Verified in QEMU.
- Fonts: bitmap fonts now cover Latin Extended-A/B, Vietnamese, general punctuation, currency and arrows. Non-Latin entry titles (Cyrillic, Greek, CJK, ...) fall back to GRUB's `unicode.pf2` (copied into the theme, loaded by `05_material` / the static block) and, in the info pills, to an installed system font. Verified in QEMU. Google Sans Flex itself has no Cyrillic/Greek/CJK glyphs.
- CI (GitHub Actions): syntax + unit + fake-`/boot` pipeline tests, installer matrix over six distro containers (dark/light, several resolutions), QEMU boot smoke test per scheme with screenshots as artifacts. New `tests/`.
- QEMU helpers find OVMF on Debian/Ubuntu/Arch/Fedora layouts (or `OVMF_CODE`), work without KVM, and no longer need ImageMagick.

Known limitations: neither GitHub workflow had run in a release before this tag; `--prebuilt` is untested on an immutable host; `blscfg` calls with `--path`/`--show-*` options are left untouched (entries are themed by class only, no pills or Advanced grouping).

## 0.2.0 (2026-11-16)

Highlights: light scheme, native 4K scenes, five more resolutions, experimental immutable-distro support, contributor docs.

**Fixes (from #1 / #2)**
- Fedora entries rendering grey: mirrored BLS entries kept blank lines, and GRUB's parser stops at the first one, so `grub_class` was never read. Blank lines are dropped.
- Crash/race when the installer, `grub-mkconfig` and the systemd path unit ran the post-processing at once (left entries without scenes): runs are serialised with `flock`, and mirror directory creation is tolerant.
- Resolution auto-detection picked the first connected display; the largest connected one now wins. Unsupported sizes (e.g. 1366x768) snap to the nearest built-in bundle before building.

**Added**
- Experimental immutable (ostree/bootc) support: `/var/lib/material-grub` layout, direct edit of the static `grub.cfg` (`material-grub-static`), mirrors outside `/boot/loader`, a shutdown-time refresh unit, a raw "All boot entries" safety submenu, podman build of the package, `--pkg`, `--dist-out`, `--yes`, `--immutable`. Replaces the old refusal. Not tested on a real ostree boot.
- ostree entry titles (`Fedora Linux 44.x (Silverblue) (ostree:0)`) parse into proper info pills.
- Contributor docs: `docs/adding-a-distro.md`, issue templates (bug report, distro request) and a PR template.
- Light scheme: `sudo ./install.sh --scheme light` (`package.py --scheme light`, `make package SCHEME=light`). Dark remains the default. Separate render cache (`build/scenes-light`).
- Native 2160-high scene sets (`16x9@2`, `16x10@2`, `21x9@2`) for screens 1800+ px high instead of a 2x upscale; every hero/pill/rail coordinate scales with scene height. Glyph masks are rendered at 512 px.
- New resolutions: 2880x1800, 3840x1600, 5120x2160 and a 32:9 scene set (3840x1080, 5120x1440).
- The installer (and `package.py --res`) builds only the scene set for the chosen resolution.

Known limitations: immutable support and the 5120-wide resolutions have not been booted on real hardware (QEMU/OVMF cannot create 5120-wide modes); the GRUB-rewriting step is verified on Fedora 44 only.

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
