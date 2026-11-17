# Ventoy support plan

Status: IMPLEMENTED as `install/bin/material-grub-ventoy` and verified in QEMU/OVMF with real Ventoy 1.1.18 (see "Verified" below). Not yet: installer/TUI integration (`install.sh --ventoy`), CI job, README gallery, real hardware. Items marked (?) are still unknown.

## Decision: dynamic by default (maintainer, 2026-11-17)
The theme cannot be re-rendered when someone copies an ISO onto the stick from any other PC, so the default mode (`MODE=dynamic`) needs no knowledge of the files:
- one pre-rendered scene per catalog distro (+ Ventoy's own menus), matched by ~610 generic `menu_class` rules (every alias/title in four letter-cases, longest first; Windows 10/11 patterns);
- `rail` = three section slots (Linux / Windows / Tools), `clean` = the panel without the neighbour peeks, `list` = per-distro hero on the left and the ROWS DRAWN BY GRUB (two synchronised native boot_menus: translucent pill rows + text), so any number of ISOs works and scrolls;
- trade-offs: the highlight colour of list rows is neutral (GRUB colours are global), no per-row distro icons, no section dividers in the list, no neighbour peeks in `clean`.
`MODE=snapshot` keeps the install-time render (pixel-exact list/clean from the ISOs present; re-run the tool after changing the files; unknown files fall back to a list with no highlight).

## Goal
Same theme on a Ventoy stick as on a PC: rail / clean / list styles, dark / light, cookie, logo, hints, per-distro colours and logos, name-based matching.
The cookie shows a static Ventoy logo instead of the BGRT firmware logo (a stick has no single machine).

## Facts (from ventoy.net plugin_theme / plugin_menuclass)
- Ventoy takes a standard GRUB `theme.txt` (`theme.file`, string or array), fonts as `.pf2` paths (`theme.fonts`), `gfxmode`, `ventoy_left/top/color` for its own version string.
- `theme.file` array + `resolution_fit: 1` (1.0.86+) picks the theme whose path contains `WxH`.
- `menu_class`: `key` = case-sensitive substring of the ISO file name, `parent`/`dir` = folder, first match wins, `class` max 128 chars. Icons: `<theme>/icons/<class>.png`.
- Placeholders usable in theme.txt: `@VTOY_HOTKEY_TIP@`, `@VTOY_MEM_DISK@`.
- Not documented (?): icon size/format, boot_menu behaviour, menu ordering, full list of built-in classes.

## Design: render at install time, from the stick's real contents
The PC pipeline is: scan entries -> classes -> menu.json -> bake one scene per entry. Ventoy gets the same pipeline with a different scanner:

1. `material-grub-ventoy` (new, stdlib + Pillow, no root once mounted) scans the stick for ISO/WIM/IMG/VHD/EFI files and folders.
2. Names go through the existing `mgrub.key_for` (case-insensitive tokens, Windows 10/11 by name, Tux fallback). Output: exact `menu_class` entries (`key` = full file name, so Ventoy's case-sensitive substring rule cannot miss) plus `entries.json` / `menu.json` in the same format the PC tools write.
3. `mgscenes.Renderer` (already pure) bakes per-entry scenes for the chosen STYLE; `clean` and `list` get their neighbours from `menu.json` in Ventoy's real order (?).
4. Files not on the stick at install time (added later) fall back to class scenes (no neighbours / no pills). Re-run the installer to refresh. A small case-variant fallback `menu_class` list covers new ISOs; kept short because Ventoy warns long lists slow the menu.
5. Folder, back, tools and F4/F5 entries use fixed scenes: `vtoydir`, `vtoyret`, `vtoyiso/wim/img/efi/vhd` fallbacks, power entries reuse Restart / Shut down, local-boot reuse Windows / Firmware (?: full class list from Ventoy source).

## Options parity
Same conf keys as the PC (`STYLE`, `SCHEME`, `COOKIE`, `LOGO`, `HINTS`, `RAW_NAME`, `COUNTDOWN`, `TIMEOUT`), stored on the stick in `/ventoy/material-grub.conf`.
- `LOGO=on` draws a static Ventoy logo in the cookie. Licence of the Ventoy logo is unchecked (?). Fallback: a Material "V" mark we draw ourselves, or a user-supplied image.
- HINTS: PC hints (Enter / e / c) are wrong on Ventoy. Ventoy variant uses its own keys (F1 help, F2 browse, F3 tree/list, F4 local boot, F5 tools, F6 ext menu, F7 text mode) either baked or via `@VTOY_HOTKEY_TIP@`.
- COUNTDOWN / TIMEOUT: Ventoy has its own timeout setting (`control` plugin); map TIMEOUT to it (?).
- Colours: the catalog seeds stay; `--seed KEY=#hex` override is optional.

## Resolution
Unknown machines, so ship several themes: `/ventoy/themes/material_WxH/` per chosen resolution, `resolution_fit: 1`, `default_file: 0`. TUI step is a multi-select of resolutions (default: the detected monitor plus 1920x1080). Cost is the main variable: 2160-high sets are about 20 MB each.

## Installer
- `./install.sh --ventoy [MOUNTPOINT]`, TUI gets a first question "This PC's GRUB / Ventoy USB" and a stick picker (lsblk, label `Ventoy`).
- Builds from source as now (deps need the package manager, so root only for that step), renders into the stick.
- Merges into `/ventoy/ventoy.json`: only `theme` and `menu_class` are touched, a `.bak` is written, `--uninstall` removes our entries and folders.
- Pure Ventoy mode never touches `/etc/grub.d`, `grub.cfg` or systemd.

## Phases
0. Research + rig: real Ventoy in QEMU/OVMF (loop device, needs sudo: ask first), dummy ISOs; settle icon size, boot_menu behaviour, menu order, class list. GATE: show screenshots of the default Ventoy menu with a trivial theme.
1. Ventoy scanner and `menu_class` generator, rail style, dark, one resolution. GATE: screenshot.
2. clean + list styles, light scheme, cookie/logo/hints variants, fixed scenes for folders, tools and F4/F5.
3. Multi-resolution + `resolution_fit`, fonts, version-string placement.
4. Installer flags, TUI, safe `ventoy.json` merge and uninstall.
5. DROPPED (maintainer decision): no pills parsed from ISO names. The distro is detected from the name only for colour and logo; the displayed name is the raw ISO file name from Ventoy. Applies to all three styles.
6. Tests (unit: matcher, `ventoy.json` merge; QEMU boot per style), CI, README with a verified / unverified list.

## Phase 0 results (verified 2026-11-17, Ventoy 1.1.18, QEMU/OVMF, no root needed)
- Test stick without root: 520 MiB MBR image, partition 1 FAT32 (filled with `mformat`/`mcopy`, mtools), partition 2 = `ventoy/ventoy.disk.img.xz` from the release tarball (32 MiB, type boot), first 446 bytes of the MBR = `boot/boot.img`. Without the boot code Ventoy says "MBR check failed". Boots in OVMF.
- Default menu is 1024x768, items are sorted case-insensitively (archlinux, debian, Fedora, ubuntu, Win11). Hotkey bar: L:Language F1:Help F2:Browse F3:TreeView F4:Localboot F5:Tools F6:ExMenu (F7 not shown in 1.1.18).
- The existing theme works unchanged as a probe: `theme.file` + `gfxmode` + `fonts` + `menu_class` (key = substring of the ISO name -> `icons/<class>.png`) gave the full-screen distro scene, selection changes swap the scene, and the raw line at the bottom shows the ISO file name. Fedora, Arch verified; Ubuntu, Debian, Win11 not looked at yet.
- Phase 1 verified (rail, dark, 1920x1080, real Ventoy 1.1.18 in QEMU): 8 ISOs on a fake stick (incl. one in a subfolder) show the right distro scene, Windows 10 vs 11, Ventoy key hints, static "V" logo in the cookie, raw ISO name on the bottom line. The list order is case-insensitive by file name and flat (a subfolder's ISO is listed with the rest in list view).
- `menu_class` matcher facts (verified): `key` is a case-sensitive proper substring of the file name; a key equal to the WHOLE name never matches; keys up to 31 chars work, 32+ are ignored; a class without a matching `icons/<class>.png` gives a blank screen, not a fallback. The tool therefore picks, per file, the longest unique proper substring of at most 30 chars (`pick_key`).
- Still unknown: tree view (F3) rows, F2/F4/F5 menus and their classes, what Ventoy draws over the scene (version string, hotkey bar), non-ISO classes (`vtoydir`, `vtoyret`...), behaviour at other resolutions.

## Verified (QEMU/OVMF, Ventoy 1.1.18, no root)
rail / clean / list x dark / light in dynamic mode; snapshot rail / clean / list; 28 ISOs with long, Cyrillic and Japanese names (list scrolls, text ellipsised, fallback fonts); ISOs the tool never saw (dynamic); LOGO / COOKIE / HINTS / RAW_NAME off; Ventoy's F3 tree view, F4 local boot and F5 tools menus (scenes for folder, back, tools, local boot; power / firmware / Windows items reuse their scenes; the native list shows Ventoy's real entries); 1920x1080, 2560x1080 and 3840x2160 themes with `resolution_fit` (the matching theme is picked when `gfxmode` equals a theme folder's resolution).
Findings: `gfxmode: "max"` gave a broken display in QEMU (use an explicit mode); GRUB grows pixmap-styled items downwards by the slice height and clips text to the item rectangle (hence two lists); both lists need the same `height` or the highlight drifts; empty (0 byte) ISOs are ignored by Ventoy.
Not verified: real hardware, BIOS/legacy boot, other Ventoy versions, F2 browse, F6 external menu, countdown / `TIMEOUT` (not wired), the optional real Ventoy logo (a Material "V" is drawn instead; `--logo FILE`).

## Risks
- Menu order and what Ventoy puts around the ISO list (?) decide whether `clean` / `list` neighbours match what is on screen.
- Tree view (F3) vs list view show different rows; scenes are baked for one of them, the other falls back to class scenes (?).
- Ventoy logo licence and trademark.
- Nothing is tested on real hardware or against real Ventoy yet.
