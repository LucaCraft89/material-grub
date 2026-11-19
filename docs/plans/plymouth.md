# Plymouth plan: material-plymouth, the boot splash that continues the GRUB theme

Status: PLAN ONLY (no code written yet). Waiting for the maintainer's approval of this document and for the empty repo (see "Before Phase 0").
Branch for this document: `ccr-d8df62d1-7vgvjn`. Nothing below is implemented.

## 0. The request, verbatim (source of truth for intent)

> i really love this project especially the style but it all falls apart as soon as plymouth hits because it's themed different, i want you to create a second repo material-plymouth that seamlessly integrates with this one with the same style customization and everything and that can be managed by the webgui of material grub, also to start for the style take where the main hero logo was on the material theme leave it there along with the background chips and title name but replace the list where there is a list or add depending on the style, the squigly animated loading bar of material 3 expressive, also since we use Plymouth now animate the bgrt cookie which i forgot to mention has to stay along with the rest that stays, if it a cookie and not a pill the cookie of the distro, in the centered list version keep the selected distro entry and get rid of the other, animate the wallpaper and its shapes as well, but first read the entire repo and its state then plan it out first prompting me for every doubt i rather you prompt me than do something i did not ask for

## 1. Decisions (maintainer, this session; do not re-ask)

| # | Question | Answer |
|---|---|---|
| 1 | Where does it live? | A separate, empty repo `LucaCraft89/material-plymouth`, created by the maintainer; the assistant attaches it (`add_repo`) and pushes there. |
| 2 | How does Plymouth know the distro? | **Per installed OS.** The theme is generated on each distro from its own `os-release` and the `key` rules of `overrides.json`. GRUB passes nothing on the kernel command line. Consequence: `class` and `title` override rules cannot apply in Plymouth (it never sees the GRUB title); `doctor` says so when such a rule is the only thing customising the booted distro. |
| 3 | Shared code | **Extract later, depend now.** Phase 1: material-plymouth imports from the installed material-grub package through one thin adapter module. Phase 2 (after Plymouth works and is released): move the shared modules to a third repo and switch both over. Nothing moves in material-grub before then. |
| 4 | Systems | Fedora (dracut), Debian/Ubuntu (initramfs-tools), Arch (mkinitcpio), openSUSE (dracut). Immutable/ostree systems are **not** in the first release (their initramfs is built by `rpm-ostree`); to be asked at the end. |
| 5 | What stays from the GRUB scene | Hero (distro glyph in its card, same position) and the title; the **info pills** (without the kernel pill, see 9); the BGRT logo in the top-right cookie; the background, same layout but animated. The rail, the clean peek panels and the key-hint pills are navigation, so they are dropped. |
| 6 | Motion | All four: slow rotation, shape morph, gentle drift/breathing, hero pulse. |
| 7 | Wavy bar | Both, by option: `PLYMOUTH_BAR=indeterminate|progress`. |
| 8 | List style | Collapse the list to the **selected row only** (cookie with the glyph, name pill) with the wavy bar directly under it, then the pills. Split: the same on the right half; the hero stays on the left. |
| 9 | Kernel pill | **None** in Plymouth (the theme is shared by every kernel's initramfs, so it would be wrong after an update). OS name, version, edition and "Default" pills stay. |
| 10 | Cookie | The top-right cookie keeps the BGRT logo (Tux when the firmware has none) and now animates. The distro's cookie in the list/split row animates too. The hero card in rail and clean stays a card. |
| 11 | Other screens | Boot splash, **disk password prompt** (mandatory: without it LUKS cannot be unlocked), shutdown/reboot, updates and messages. |
| 12 | Kernel command line | Add `splash` (and `quiet`) only if missing, after asking; with a backup; removed on uninstall; `--yes` accepts. |
| 13 | Initramfs rebuild | Backup, rebuild, verify, restore on any failure (same pattern as `mgsafe`). |
| 14 | Settings | **Shared by default**: style, scheme, seed colour, per-distro colour/name/icon, cookie and logo come from the existing `/etc/material-grub.conf` and `overrides.json`. New Plymouth-only keys live in the same conf. An independent-look toggle can come later. |
| 15 | Command | No second command. `material-grub plymouth apply | status | remove | preview` (one-command rule of 0.7.1). |
| 16 | Deliverable now | This plan only. |

## 2. What the repo is today (facts that constrain the design)

- The theme is a stack of **pre-rendered PNG scenes**. `scripts/build_theme.py` renders backgrounds and class scenes at build time; `install/bin/mgscenes.py` (`Renderer`, Pillow only) draws hero, pills, rail, cookie and hints at config time, and redraws panels for custom colours (`Renderer.panel_scene`). Every coordinate is a 1080-high design value passed through `u()`.
- Layout constants a Plymouth scene must reproduce (1080-high design): hero card 600x320 / 560x280 at y=360 (centred), glyph 230, title at y=590 (tsz 150 down to 60, weight 800), pills row at y=672 (h 58); countdown bar 560 wide at y=755; top-right cookie 230 px at (W-150, 140) holding a 120 px logo; background shapes: cookie 620 at (cx-0.36W, H-120), sunny 460 at (cx+0.34W, H-60), clover 300 at (cx-0.29W, 150). List: column 640, rows 76, row shape = `opts.shape` (cookie), name pill 64 high; split: list at 0.47W, hero centred at (0.25W, 450) in a 400 cookie.
- Colour: `mgpalette.scheme(seed, dark)` is the vendored pure-Python `materialyoucolor`; `palettes.json` holds the per-entry palettes; `overrides.json` (`seed`, `entries[]` with `key|class|title` matches) is read by `mgoverrides.load()` and never breaks a boot.
- Conf: `/etc/material-grub.conf` through `mgrub.load_conf` / `write_conf`; keys `STYLE COOKIE LOGO HINTS RAW_NAME COUNTDOWN TIMEOUT SCHEME MODE`. `install/systemd/material-grub.path` already re-applies when the conf or overrides change.
- The BGRT logo is converted by `scripts/bgrt-logo.py` (stdlib) to a tinted silhouette PNG at config time; Tux is the fallback (`Renderer.machine_logo`).
- GUI (optional package `material-grub-gui`): stdlib server + vanilla ES modules; `gui/web/ui.js` already has `WavyProgress` (travelling sine wave, determinate and indeterminate), which is the reference for the bar's geometry. Root only through `pkexec` on `gui/mghelper.py`, which accepts a fixed verb list (`apply`, `update`) and a fixed list of conf keys. The preview is the same `Renderer` code that writes the real menu.
- Safety pattern to reuse: `mgsafe.guarded` (backup, validate, roll back, report to journal/`wall`/`last-error`), `/var/backups/material-grub`, one lock shared with the path unit.
- Nothing in the repo mentions Plymouth or `splash` yet.

## 3. Constraints Plymouth imposes (what GRUB did not have)

1. **It runs in the initramfs.** The theme must be inside every initramfs, so applying means rebuilding it (`dracut -f`, `update-initramfs -u -k all`, `mkinitcpio -P`) after `plymouth-set-default-theme`.
2. **The script module** is Plymouth's only scriptable engine: sprites (`Image`, `Sprite`), `Image.Scale/Rotate`, `Math.*`, a per-frame refresh callback, boot-progress, password, message and mode callbacks. No vector drawing, no filters. So: Python/Pillow renders the **static assets** at apply time (nothing is built in the initramfs), the script animates them.
3. **Text without fonts.** Plymouth text needs the label plugin, pango and fonts inside the initramfs. Instead the title, pills, password placeholder, "Shutting down", "Restarting" and update messages are **pre-rendered PNGs** in Google Sans Flex (with the existing non-Latin fallback logic).
4. **The progress value is not real.** Hence the two bar modes.
5. **Resolution.** Plymouth uses the display's native DRM mode; GRUB uses `gfxmode`. Assets are rendered for the monitor's native size (`monitors.detect`) and the script scales to the real screen as a fallback, so there is no jump when the modes differ.
6. **Initramfs size.** Morph frames and rotation sprites cost bytes. Budget to be measured in Phase 0 (target: under 2 MB of assets at 1080p).
7. **Windows, Ventoy, Firmware, Restart, Shut down entries** never reach a Linux Plymouth. Out of scope.
8. **Script-module availability.** `plymouth-plugin-script` is a separate package on Fedora and some others; `doctor` and the installer check for it.

## 4. Architecture

```
material-grub (this repo)                         material-plymouth (new repo)
 mgrub / mgoverrides / mgpalette / catalog  <---  adapter.py (the ONLY file that imports material-grub modules)
 mgscenes.Renderer (hero, pills, shapes)    <---  renderer: scene assets per style, wave, shapes, password, messages
 GUI: Plymouth page, preview, helper verb   --->  `material-grub plymouth ...` plugin entry point
 conf + overrides.json (shared)                    theme/ (material.script, material.plymouth, generated PNGs)
                                                   hooks: dracut, initramfs-tools, mkinitcpio, kernel-cmdline, uninstall
```

Apply flow (`material-grub plymouth apply`, root, under the shared lock):
1. Read conf + overrides; resolve the booted distro (`/etc/os-release` `ID`, `ID_LIKE`, `NAME` through the catalog rules, then the matching `key` override rule; unknown Linux falls back to Tux, as in GRUB).
2. Render the asset set for the native resolution into a staging directory: background shapes, hero card + glyph, title and pill PNGs, cookie + BGRT logo, wave tiles/segments, password field, message strings, morph frames.
3. Install into `/usr/share/plymouth/themes/material/` (staged then swapped), `plymouth-set-default-theme material`.
4. Check the kernel command line for `splash`; show and ask, then add with a backup.
5. Back up the current initramfs images and theme, rebuild, verify each image lists the theme files and is non-empty, otherwise restore and report through `mgsafe`.

`material-grub plymouth remove` restores the previous theme, the command line and the initramfs.

## 5. Scenes per style (Plymouth)

All scenes use the palette of the booted distro (or the single seed) and the GRUB design coordinates, so GRUB hands over to Plymouth with the hero, title and pills where they were.

- **rail** and **clean**: same background and hero card + title + info pills; the wavy bar is **added** at the old countdown position (y=755, 560 wide). No rail, no peek panels, no hints.
- **list**: the list collapses to the selected row (rotating cookie with the glyph, name pill), the wavy bar directly under it, then the info pills.
- **split**: hero on the left (cookie with glyph, title, pills), the selected row and the wavy bar on the right.
- All styles: the top-right cookie with the BGRT logo (`COOKIE`/`LOGO` respected).
- `RAW_NAME`, `COUNTDOWN`, `HINTS` have no meaning in Plymouth and are ignored there.
- **Password prompt**: the same scene, the bar replaced by an M3 pill input with dots, a lock hint and a wrong-password shake. Always available, independent of `STYLE`.
- **Shutdown / reboot / update**: the same scene with a pre-rendered "Shutting down", "Restarting" or "Installing updates" line under the title.

## 6. Motion model (script module)

| Element | Motion |
|---|---|
| Background shapes (cookie, sunny, clover) | slow rotation at different speeds and directions, plus drift and scale breathing on an eased loop |
| Top-right cookie | slow rotation; the logo stays upright |
| Cookie in the list/split row | the same, plus a **morph** through the M3 shapes (cookie, flower, sunny, clover) from pre-rendered frames |
| Hero card | scale-in at start, then a small breathing pulse |
| Wavy bar | travelling sine wave drawn from sprites; `indeterminate` (a segment loops) or `progress` (the active part follows Plymouth's boot progress, easing so it never jumps back) |
| `prefers-reduced-motion` | no equivalent in Plymouth: a conf key `PLYMOUTH_MOTION=full|calm|off` (calm = slow rotation only, off = static) |

New conf keys (same file): `PLYMOUTH=on|off`, `PLYMOUTH_BAR=indeterminate|progress`, `PLYMOUTH_MOTION=full|calm|off`.

## 7. Integration with material-grub (the only changes in this repo)

1. `install/bin/mgrub.py`: `CONF_DEFAULTS`/`CONF_CHOICES` and `_conf_ok` for the three keys; `tui.py CHECK`, `cmd_doctor`, `gui/mgstate.CONF_KEYS`, `gui/mghelper.CONF_KEYS` and the sample `material-grub.conf` updated; tests extended.
2. `install/bin/cmd_cli.py`: `plymouth` subcommand that finds the plugin (`/usr/share/material-plymouth/bin`, else `MATERIAL_PLYMOUTH`) and dispatches; the menu TUI and `doctor` show it only when installed. No new command is installed.
3. `gui/mghelper.py`: a new fixed verb `plymouth` (`apply`, `remove`) that validates its input and calls `material-grub plymouth ...`; the polkit policy is unchanged (same helper).
4. GUI: a **Plymouth** page, visible only when the plugin is installed: on/off, bar mode, motion level, still preview of boot, password and shutdown screens (drawn by the real renderer through a new `/api/plymouth/preview`), and an animated browser preview that plays the real assets with the same motion model (reusing `WavyProgress`). Style, scheme, colours and entries stay on their existing pages and are shared. Apply uses the existing progress dialog and event stream.
5. Docs, CHANGELOG, `docs/gui.md`, `docs/how-it-works.md` (the table "Not possible in GRUB" gets a pointer: the wavy bar and animation now exist, in Plymouth), CI.
6. The material-grub package never depends on, recommends or installs material-plymouth (same rule as the GUI package).

## 8. Packaging (material-plymouth repo)

Sources only, rendered on the target like the main package: rpm (`%posttrans`, dracut), deb (`postinst`, initramfs-tools hook), arch (`post_install`, mkinitcpio hook and pacman hook). It requires `material-grub` of a compatible version (checked by `adapter.py` and `doctor`) and the distro's script plugin. `install.sh` for source installs. Same CI shape as material-grub (lint, unit, containers on Fedora/Ubuntu/Debian/Arch/openSUSE).

## 9. Phases (each one a green, reviewable step)

0. **Spike (needs your go).** One script theme with a rotating cookie, shapes and the wavy bar, run with Plymouth's X11 renderer under Xvfb in this sandbox (Plymouth is installable here; QEMU is not installed and would need adding). Measures: rotation quality and CPU, wave smoothness, asset size. Decides sprite-wave vs frame-wave and the morph frame budget. If the script engine cannot do it well, I stop and report instead of building on it.
1. **Contract and conf** (material-grub): the keys, `plymouth` subcommand dispatch, doctor hooks, tests. No Plymouth needed to test.
2. **Renderer**: scene assets for the four styles, light and dark, single seed and per-distro keys, BGRT/Tux, pills, password, messages. Golden tests and screenshots, like the GRUB gallery.
3. **Script theme**: animation, bar modes, password prompt, modes (boot, shutdown, update), fallbacks.
4. **Apply/remove** with the safety pattern, per initramfs system, command-line step.
5. **GUI page and preview**, helper verb.
6. **Packaging and CI** in both repos; container tests check the built initramfs lists the theme (`lsinitrd`, `lsinitramfs`, `mkinitcpio -S`), and the dry-run diff.
7. **Boot test** in QEMU/OVMF (GRUB, then Plymouth, then login), screenshots at each handover to check nothing jumps.
8. Phase 2 of decision 3: extract the shared code into the third repo.

## 10. Verification

- Unit tests: conf keys, adapter contract, identity resolution (os-release, `ID_LIKE`, override keys, Tux fallback), scene geometry equals the GRUB geometry, asset budget.
- Visual: Xvfb + Plymouth X11 renderer screenshots per style/scheme/mode compared with the GRUB renders; the handover frame diff (last GRUB scene against the first Plymouth frame).
- Safety: failed rebuild restores the old initramfs; missing script plugin is reported, nothing changes; uninstall restores everything; a bad overrides file never stops a boot.
- Real hardware: LUKS prompt, the proprietary-GPU drivers, the GRUB-to-Plymouth mode switch and the Plymouth-to-display-manager handover are only testable on real machines; the maintainer's go and report needed, as with the GRUB theme's hardware status.

## 11. Risks

- **Script-engine limits** (rotation quality, no clipping, CPU on a simple framebuffer): the reason for Phase 0.
- **Bricking the initramfs.** Mitigated by backup, verify, restore, and by never touching the GRUB fallback entries; still the most dangerous step of the project.
- **Kernel command line edits** on BLS (Fedora): use `grubby`/`/etc/kernel/cmdline` rather than editing entries by hand.
- **Arch** needs the `plymouth` hook in `mkinitcpio.conf` placed after `base udev`; the invasive part is detected and shown first, never silent.
- **Handover jumps** if the GRUB `gfxmode` and the native mode differ (stretching) or the display manager sets its own mode.
- **Two repos drift** until the shared library exists: `adapter.py` and a version check are the guard; a CI job installs both at pinned versions.
- **Asset size** of morph frames inside every initramfs.
- **Third-party distro Plymouth packaging differences** (theme path, `plymouth-set-default-theme` absent on Debian, which uses `update-alternatives`): handled per distro and tested in containers, but only Fedora is a known-good development platform here.

## 12. Before Phase 0 (needed from the maintainer)

1. Create the empty repo `LucaCraft89/material-plymouth` and tell me, so I can attach it. Until then nothing is written there.
2. Approve this plan or change it.
3. Permission for the Phase 0 spike (installs `plymouth` and its script plugin in this sandbox only).
4. Open question: immutable/ostree systems (Silverblue, Bazzite) after the first release, or never.
