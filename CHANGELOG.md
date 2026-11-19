# Changelog

## Unreleased

Groundwork for optional parts from other packages (the first is the Plymouth boot splash, in its own repository). Nothing changes without one.

**New**
- **Optional parts (plugins):** another package can install one manifest and add a sub-command (`material-grub plymouth ...`), a menu entry and a line in `help`, `version` and `doctor`; a part that is missing, broken or written for another plugin API is reported, never fatal. See `docs/plugins.md`.
- Runtime options `PLYMOUTH`, `PLYMOUTH_BAR` and `PLYMOUTH_MOTION` in `/etc/material-grub.conf` (validated, kept in presets); they do nothing until the Plymouth part is installed.

## 0.7.1 (2026-11-18)

One command.

**Changed**
- `material-grub` is the only command that is installed (now in `/usr/local/bin`, so every user finds it). `material-grub apply` replaces `material-grub-apply`, and `material-grub gui` replaces `material-grub-gui`; `doctor`, `preview`, `ventoy` and the rest were already subcommands. An update removes the old `material-grub-apply` and the GUI package's `/usr/bin/material-grub-gui`. The kernel and pacman hooks and the GUI's helper call `material-grub apply`. What remains outside `/usr/share/material-grub` are files GRUB and polkit need at fixed paths (`/usr/libexec/material-grub-postprocess`, `/usr/libexec/material-grub-gui-helper`), not commands.

**Fixed**
- `material-grub doctor` no longer reports "no theme" and "grub.cfg not found" on Fedora, where `/boot/grub2` is readable by root only (issue #9). In a terminal it now asks sudo and checks the real files, like `apply`; from a script or the GUI it shows a warning instead of a failure.

## 0.7.0 (2026-11-18)

An optional GUI, a one-colour theme and per-entry customisation.

**New**
- **GUI** (`material-grub-gui`, a separate optional package; `sudo ./install.sh --with-gui` for source installs; never installed by the theme or the TUI): a Material 3 Expressive web UI in your browser with a live preview, drag and drop ordering, per-entry name, colour, icon and visibility, Ventoy sticks, presets, health checks and one-click updates with a progress pop-up. It never runs as root: changes go through `pkexec` to a small helper that validates every request. See `docs/gui.md`.
- **One colour for the whole theme:** pick one of 32 seed colours (or any `#RRGGBB`) and every entry uses its Material 3 palette. In the installer's TUI (new *Colours* and *Seed colour* steps, `--seed '#RRGGBB'`, `--seed-mode multi|single`) and in the GUI.
- **`/etc/material-grub/overrides.json`:** colours, names and icons per entry (your own PNG, JPEG, SVG, ...), hidden entries, section and entry order (the real GRUB menu is reordered), validated strictly when written and leniently at boot (a bad file never breaks the menu). `material-grub doctor` checks it. See `docs/customising.md`.
- **Ventoy:** the same overrides on the stick (`ventoy/material-grub-overrides.json`): per-ISO colour, icon and name (the name is drawn on the image's screen; it is also written as a `menu_alias`, which Ventoy 1.1.18 does not show in its list), and the single-colour mode.
- The installer's TUI asks whether to install the optional GUI (default no; `--with-gui` answers it).
- The firmware (BGRT) logo now shows in the cookie of the previews (the GUI's live preview and `material-grub preview`); on a real menu GRUB draws it from `machine-logo.png` as before. When the firmware has no logo (a VM, many desktops) the cookie now gets the Linux penguin instead of staying empty, in the previews and on the real menu.
- **Presets:** save the look under a name, move it to another machine as one JSON file.
- `install.sh --progress json` (machine-readable progress for tools), a persistent install log in `/var/log/material-grub/install.log`, `material-grub doctor --status-json`.

**Fixed**
- A square picture of your own no longer spills out of its white badge on an entry's screen (it is fitted into the badge). In the Ventoy snapshot list a customised file's row now carries its own name, colour and icon.
- `list` style: the countdown bar overlapped the info chips under the list (found by the new QEMU feature tests); the chips now sit between the list and the countdown.

**Changed**
- **One command:** `material-grub` is the front end for everything: `doctor`, `apply`, `gui`, `preview`, `colour`, `presets`, `overrides`, `conf`, `ventoy`, `update`, `uninstall`, `version`, `help`; without a subcommand it opens a menu. Root-only subcommands re-run through `sudo`. The old command names keep working. See `docs/cli.md`.
- The scene renderer can redraw the build's panels at apply time (`Renderer.panel_scene`, pixel-identical for backgrounds), so custom colours need no rebuild; the colour science (`materialyoucolor`, pure Python part) is vendored for the installed tools.
- `mgrub.write_conf` is the one atomic, validated writer of `/etc/material-grub.conf`.

## 0.6.0 (2026-11-18)

Safety, maintainability and packaging. The installer's logic is now Python; the theme is still always built from source on your machine.

**Safety**
- Every rewrite of `grub.cfg` is validated (`grub-script-check` plus a structure check) and rolled back when wrong. The failure is shown in a terminal box, the journal and (without a terminal) with `wall`; `/var/lib/material-grub/last-error` keeps the reason for `material-grub doctor`. A file that failed is not retried on identical input.
- A real GRUB-script parser (`install/bin/grubscript.py`) replaces the regex handling of `menuentry`/`submenu`: quotes, escapes, `}` and `{` in titles, multi-line headers, nested submenus. Golden tests use real `grub-mkconfig` output from Debian, Ubuntu, Arch and Fedora.
- The generated `grub.cfg` loads the theme only when `theme.txt` and `icons/` exist at boot; otherwise GRUB shows its plain menu.
- The theme directory is swapped in with the old one kept until the new one is in place; an incomplete new theme is dropped.
- `grub-mkconfig` and the post-processing run under one lock (a stale run could restore an old snapshot over a fresh `grub.cfg`).
- `./install.sh --dry-run`: diff of `grub.cfg` and `/etc/default/grub` plus the list of files, nothing is changed.

**New**
- `material-grub doctor` (also `material-grub-apply --status`): checks the theme, `grub.cfg`, a scene per entry, hooks, the path unit, the config and the last rollback; exit status 0/1; the bug template asks for its output.
- `./install.sh --preview` and `material-grub preview`: your own boot entries rendered as a web page, no root and nothing installed.
- The info chips show the drive (`/dev/sda5`) for os-prober entries, so two installs of one distro can be told apart (info chips now in every style: under the hero in rail, clean and split, under the list in list; in the list rows the drive is appended to the name when the same distro appears twice on a menu level, e.g. `Ubuntu (sda5)`).
- Packages (source only, the theme is built on install): `packaging/` has an Arch PKGBUILD, a Fedora spec and a Debian package, see `docs/packaging.md`.

**Changed**
- `install.sh` is a short POSIX sh bootstrap that finds or installs Python 3.8+ and runs `install/installer.py`. RHEL 8 family (python3 is 3.6) installs `python3.12` and builds with it.
- Build requirements are pinned with hashes (`requirements.in` -> `requirements.txt`, `make update-requirements`); the build needs Python 3.9+.
- Resolutions and the generic-alias set live in one place (`install/bin/resolutions.json`, `mgrub.py`).
- Ruff and shellcheck run in CI; the tools are importable modules (`install/bin/cmd_*.py`) behind the old executable names.
- Ventoy name matching: `arch`, `kali`, `mint` and `tails` only match with a separator after them (no more `archive`, `kalimba`, `mintchoc`).
- README shortened; installer details, immutable systems, how it works and customising moved to `docs/`.

## 0.5.0 (2026-11-17)

Ventoy support, a fourth style for the PC, and the Pordenone Linux User Group scene.

**Ventoy**
- `install.sh --ventoy [MOUNTPOINT]` themes a Ventoy USB stick (no root needed; `--res A,B,C` for several screen sizes, `--mode dynamic|snapshot`, `--uninstall --ventoy MOUNTPOINT`). The TUI asks "this computer's GRUB or a Ventoy stick" first, then offers the detected sticks (`install/ventoy_sticks.py`: data partition found through its VTOYEFI sibling, mounted or not; an unmounted one is mounted for the copy and unmounted afterwards), resolutions, style, scheme, logo, hints and mode. A fresh Ventoy stick has no `/ventoy` folder, so the installer creates it.
- Two styles. `full`: the ISO picker is one full-screen scene (distro logo, name, a pill with a disc icon and the real file name, the cookie with the real Ventoy logo, two small rounded arrows on the left that hint at scrolling; no rail, no neighbours, no key hints). `list`: the distro's logo and name on the left, the list on the right. In `full` every other Ventoy menu (F2 browse, F3 tree, F4 local boot, F5 tools, the boot-mode menu) is the list. `rail`, `clean` and `split` from older settings map to `full` / `list`.
- `install/bin/material-grub-ventoy` does the work and merges into `/ventoy/ventoy.json` (user `menu_class` rules stay first, backup kept, uninstall removes only its own entries). Dark and light schemes, optional cookie, logo, key hints and raw file name.
- Dynamic mode (default): nothing depends on the files on the stick. About 640 generic `menu_class` rules (every alias and title in four letter-cases) pick one pre-rendered scene per distro, and in the list style GRUB draws the rows itself, so ISOs can be added, renamed and removed on any computer. Snapshot mode renders the exact list for the files present at install time.
- Ventoy's boot-mode menu (Enter on an image) is themed: Normal, GRUB2, WIMBOOT, Memdisk, File checksum and Back each get their own colour, background and icon.
- PNLug: an image with `pnlug` in its name in any letter case (all 32 case combinations are written as rules, in front of everything else) gets the Pordenone Linux User Group's red and its horizontal logo on a white card.
- A file nothing recognises gets a neutral gray "Disk image" scene with a disc icon. More file-name hints (MX, LMDE, Leap, Gentoo, Puppy, OpenBSD, Windows media names); `tests/iso_names.txt` checks about 150 realistic names.
- How the full-screen picker coexists with the list: GRUB's list lies below the scene; the scenes of the other menus have holes where the rows are, the opaque ISO scenes hide it, and the file name (a GRUB label) shows through a hole in the ISO scenes' pill.
- Verified in QEMU/OVMF with real Ventoy 1.1.18: both styles, dark and light, 28 ISOs with long/Cyrillic/Japanese names, F3 tree, F4, F5, the boot-mode menu, 1920x1080 / 2560x1080 / 3840x2160 with `resolution_fit`, and `tests/ventoy_smoke.py` (install, then add/rename/remove ISOs without re-running: the right scenes appear and no file under /ventoy changes). Not verified: real hardware, BIOS boot, other Ventoy versions, mounting an unmounted stick, F2 browse, F6, countdown/`TIMEOUT` on Ventoy.

**PC**
- New fourth style `STYLE=split` (`install.sh --style split`): the centred list moved to the right, the selected entry's logo in a big cookie and its name on the left (Advanced / Rescue show their gear / wrench). Every row keeps its themed icon-in-a-shape, highlight colour and the separators between Linux, Windows and System.

**Other**
- Fixed: the missing-glyph check used a cache keyed by `id(font)`, which Python reuses; non-Latin names could render as boxes. Fallback fonts that are variable (Noto) now use the pills' medium weight instead of their thinnest.
- New scene-only catalog entries `iso` and `pnlug` (not matched by name on a PC, not in the gallery); `palettes.py` uses the Monochrome scheme for near-grey seeds. New glyphs: folder, arrow_back, play_arrow (Material Symbols, Apache-2.0). The Ventoy and PNLug logos are in `vendor/` (see `THIRD_PARTY.md`).
- Docs: the README gallery moved to `docs/gallery.md` (two screenshots of every style in dark and light for the PC and for Ventoy), Ventoy has its own page `docs/ventoy.md`, the README links to both. New `scripts/make_ventoy_screenshots.py`, `make_screenshots.py --styles`, `docs/plans/ventoy.md`.

## 0.4.0 (2026-11-17)

Runtime styles (rail, clean, list), TUI installer, distro gallery. Prebuilt downloads removed.

- Phase 0, no visual change: the top-right cookie and the key-hint pills are no longer baked into the release images; `material-grub-scenes` draws them at install/apply time. New shared renderer module `install/bin/mgscenes.py` (importable, Pillow only). `/etc/material-grub.conf` gains `STYLE`, `COOKIE`, `HINTS` (and `SCHEME`, informational); `COOKIE=off` also hides the logo. `--no-hints` now writes `HINTS=off` (works with `--prebuilt` too; at package build time it is a no-op). New `install/install.sh --set KEY=value`. Checked: with the same package inputs the scenes GRUB uses are pixel-identical to v0.3 at 1920x1080 and the cookie/hints code is identical at 2x scale.
- `material-grub-classes` writes `menu.json` (entries in real menu order per menu level) and gives plain entries (Windows, Firmware, Restart, Shut down) their own unique class in addition to the shared one, so duplicates can be told apart. Installs annotated by older versions keep the old classes until grub.cfg is regenerated.
- Phase 1: `STYLE=clean` (full screen without the rail: the previous/next entry of the same menu level peek in above and below in their own colours, label chips on the panel edges, wrapping at the ends). The BGRT logo overlay moves with the cookie; plain entries get per-entry scenes. Verified in QEMU (1920x1080, dark and light, BLS Advanced submenu); other resolutions not yet.
- Phase 2: `STYLE=list` (the whole menu level is baked into each entry's scene: icon in a cookie shape plus name in a pill, gear/wrench before the name for Advanced/Rescue, selection box and background in the selected entry's palette, section dividers wherever the menu order changes group, windowing with "+N more" chips beyond about 7 rows, countdown moved below the list). Verified in QEMU at 1920x1080 (dark and light, all entries), 1920x1200, 2560x1080 and 3840x1080 (dark); 2160-high sets and real hardware not yet.
- Phase 3: monitor detection (`install/monitors.py`: xrandr primary, GNOME/KDE/wlroots Wayland as the sudo user, DRM sysfs, `GRUB_GFXMODE`), curses TUI installer (`install/tui.py`, plain-prompt fallback) started by `install.sh` when choices are missing; new flags `--style`, `--cookie/--no-cookie`, `--logo/--no-logo`, `--hints`, `--tui`, `--no-tui`. Tested with fixtures and a pty at 80x24; not run on real multi-monitor or Wayland sessions.
- Phase 4: distro gallery: `scripts/gen_distro_table.py` renders a sample scene per catalog entry (54) from the shared renderer into `docs/distros/`, generates `docs/distros.md` (full table) and a grid in the README; CI job `gallery` fails when the tables or the image list are stale (PNG bytes are not compared), `workflow_dispatch` regenerates the images as an artifact. The GitHub jobs have not run yet.
- Phase 5: `tests/boot_smoke.py` takes a style; CI boots rail, clean and list in dark plus rail and list in light. Locally verified in QEMU (dark): all three styles at 1920x1080, 2560x1080 and 3840x2160; list also at 1920x1200 and 3840x1080 (screenshots, not the automated test). NOT verified: 5120-wide modes (OVMF cannot create them), real hardware, real ostree boot, list/clean on a classic Debian-style menu in QEMU (only the fake-/boot pipeline test), light scheme beyond 1920x1080, the GitHub workflows themselves.
- Prebuilt downloads are gone: `--prebuilt`, the TUI install-source step and `release.yml` (release assets, `SHA256SUMS`) are removed; the installer always builds from source (`--pkg DIR` still installs a package built elsewhere).
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
