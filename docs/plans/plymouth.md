# Plymouth plan: material-plymouth, the boot splash that continues the GRUB theme

Status: PLAN ONLY (no code written yet). Repos created and attached; process agreed (1b). Updated after the maintainer's second message (consistency rule, customisation recon, repo names, CI and QEMU for all distros). Waiting for approval and for the empty repos (see "Before Phase 0").
Branch for this document: `ccr-d8df62d1-7vgvjn`. Nothing below is implemented.

## 0. The request, verbatim (source of truth for intent)

> i really love this project especially the style but it all falls apart as soon as plymouth hits because it's themed different, i want you to create a second repo material-plymouth that seamlessly integrates with this one with the same style customization and everything and that can be managed by the webgui of material grub, also to start for the style take where the main hero logo was on the material theme leave it there along with the background chips and title name but replace the list where there is a list or add depending on the style, the squigly animated loading bar of material 3 expressive, also since we use Plymouth now animate the bgrt cookie which i forgot to mention has to stay along with the rest that stays, if it a cookie and not a pill the cookie of the distro, in the centered list version keep the selected distro entry and get rid of the other, animate the wallpaper and its shapes as well, but first read the entire repo and its state then plan it out first prompting me for every doubt i rather you prompt me than do something i did not ask for

## 1. Decisions (maintainer, this session; do not re-ask)

| # | Question | Answer |
|---|---|---|
| 1 | Where does it live? | A separate, empty repo `LucaCraft89/material-plymouth`, created by the maintainer; the assistant attaches it (`add_repo`) and pushes there. |
| 2 | How does Plymouth know the distro? (refined in 1a) | **Per installed OS.** The theme is generated on each distro from its own `os-release` and the `key` rules of `overrides.json`. GRUB passes nothing on the kernel command line. Consequence: `class` and `title` override rules cannot apply in Plymouth (it never sees the GRUB title); `doctor` says so when such a rule is the only thing customising the booted distro. |
| 3 | Shared code | **Extract later, depend now.** Phase 1: material-plymouth imports from the installed material-grub package through one thin adapter module. Phase 2 (after Plymouth works and is released): move the shared modules to a third repo, `material-boot-core` and switch both over. Nothing moves in material-grub before then. |
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
| 17 | End state, once `material-boot-core` exists (maintainer, third message) | **One unified installer** with options for what to install and what not (GRUB theme, Plymouth theme, GUI, Ventoy, ...), and **one command, `material-boot`**, with the sub-commands `grub` and `plymouth`, each with its own sub-commands, fully modular the way `material-grub` already is today (each part registers its own sub-commands; a part that is not installed simply is not there). See 9b. |
| 18 | Versions (maintainer, after phase 6) | **The three repositories are level and start at 1.0.0:** `material-grub` (from 0.7.1), `material-plymouth` and `material-boot-core`. Packages of one release require each other at the same major (`material-grub >= 1.0.0`). From there each moves on its own number, but a release of one that needs a change in another says so in its requirement. The migration steps that belong to this release are "since 1.0.0". The integration branch keeps its old name `release/0.8.0` until it is renamed on GitHub (open PRs follow a rename). |

## 1a. The consistency rule and the customisation recon (maintainer, second message; goes first)

**Rule: every customisation the user made for GRUB must show up in Plymouth too. Turning something off in GRUB turns it off in Plymouth.** A BGRT logo switched off disappears from the Plymouth cookie, a colour override colours the Plymouth scene, and so on for every option below. The only exceptions are options that have no meaning without a keyboard or a menu; those are listed explicitly and marked with a proposed behaviour (veto any).

How it is enforced, not just intended:
- **One resolver.** `adapter.look(conf, overrides, os_release)` returns the single "look" of the booted distro (palette, name, icon, cookie on/off, logo on/off, style, scheme, shape). Plymouth renders only from that structure, and the consistency tests (section 10) compare it with what GRUB's `cmd_scenes` resolves for the same entry. No Plymouth code reads `conf` or `overrides.json` directly.
- **A parametrised test matrix** runs every option below, on and off, through both resolvers and fails when they differ.
- **`doctor`** reports a customisation that Plymouth cannot honour (for example, a `class` rule that is ambiguous for this OS).

### Recon: every customisation that exists today, and what Plymouth does with it

Runtime options in `/etc/material-grub.conf` (`mgrub.CONF_DEFAULTS`):

| Option | GRUB today | Plymouth |
|---|---|---|
| `STYLE` rail / clean / list / split | four layouts | **Follows.** Scenes per style (section 5). `full` is Ventoy-only and never applies. |
| `SCHEME` dark / light | baked at build time | **Follows** (read from the package's `scheme.txt`, like GRUB). Changing it needs the same reinstall; Plymouth is re-rendered by that apply. |
| `COOKIE` on/off | top-right cookie | **Follows.** Off: no cookie at all, and no logo either. |
| `LOGO` on/off | firmware (BGRT) logo in the cookie | **Follows.** Off: the cookie stays, empty, as in GRUB. The Tux fallback applies only when the logo is on and the firmware has none. |
| `HINTS` | key-hint pills | **No equivalent** (no keyboard in Plymouth). Ignored. |
| `RAW_NAME` | raw GRUB entry title at the bottom | **No equivalent** (Plymouth never sees the GRUB title). Ignored. |
| `COUNTDOWN` | "Booting in N seconds" bar | **Proposed:** ignored. The wavy bar is a loading indicator, not a countdown, so it stays when `COUNTDOWN=off`. |
| `TIMEOUT` | menu timeout | n/a. |
| `MODE` dynamic / snapshot | Ventoy only | n/a. |
| `MG_LIST_SHAPE` (env knob, default `cookie`) | shape of the list row | Follows if it ever becomes an option; Plymouth reads the same value through the resolver. |

Overrides in `/etc/material-grub/overrides.json` (`mgoverrides`):

| Override | GRUB today | Plymouth |
|---|---|---|
| `seed` `multi` | every distro keeps its brand colour | **Follows.** |
| `seed` `single` + colour (32 presets or any `#RRGGBB`) | one Material 3 palette for every entry | **Follows**, through the same vendored `mgpalette`. |
| entry `color` | per entry/distro colour | **Follows** (`key` rules; `class`/`title` rules, see below). |
| entry `name` | the title on the scene, the row name | **Follows**: the title and the name pill are rendered from the override. |
| entry `icon`: catalog key | the glyph in hero, list row, rail | **Follows.** |
| entry `icon`: `file:NAME` | your picture, full colour on a white badge on the entry's screen and one-colour in rows | **Follows**, same badge rules; SVG still needs `rsvg-convert`. |
| entry `hidden` | removed from the GRUB menu | Does **not** hide Plymouth: the OS still boots and still shows its splash. |
| `groups`, `order` | menu order and rail sections | n/a (no menu). |
| match by `key` | every entry of a catalog distro | **Follows**. |
| match by `class` or `title` | one entry / entries whose title contains the text | **Follows when unambiguous** (refinement of decision 2, still "per installed OS"): at apply time the adapter resolves the rules against this OS's own entries in `entries.json`. If every entry of the booted OS resolves to the same effective rule, that rule is used; if they differ (for example one kernel entry is customised and the others are not), `key` rules win and `doctor` warns. |
| the same distro installed twice (os-prober `where`) | rows tell the drive apart | The booted install is the entry without `where`; its rule is used. |
| `version` / bad file | a bad file is ignored, reported by `doctor` | Same: Plymouth falls back to the defaults and never blocks a boot. |

Build/install-time choices:

| Choice | Plymouth |
|---|---|
| Resolution (`--res`, 12 built-in sizes, aspect sets, native 2160-high sets) | Plymouth renders for the monitor's native mode (`monitors.detect`), using the same scale rules as the GRUB scenes (`u()` and design coordinates). |
| Presets (`mgpresets`, `CONF_KEYS`) | The three new Plymouth keys join `CONF_KEYS`, so a preset (and its export/import) carries the Plymouth look too. |
| Installer TUI answers (`--style --scheme --cookie --logo --hints --seed --seed-mode ...`) | Unchanged. The TUI asks nothing about Plymouth; it is driven by the `material-grub plymouth` subcommand and the GUI page. |
| Immutable systems | Not in the first release (decision 4 asks again at the end). |

New Plymouth-only keys (decision 14): `PLYMOUTH`, `PLYMOUTH_BAR`, `PLYMOUTH_MOTION`.

### When Plymouth is re-applied (so the two never drift)

GRUB re-applies by itself when `/etc/material-grub.conf` or `overrides.json` change (`material-grub.path`). Plymouth cannot do that blindly, because every re-apply rebuilds the initramfs. So:
- The path unit also runs `material-grub plymouth apply --if-changed`.
- It computes a **hash of the resolved look** (the adapter's `look()` output, the icon files it uses, the firmware logo, the plugin version) and exits at once when the hash equals the one stored in `/var/lib/material-plymouth/state.json`. Only a real change renders assets and rebuilds the initramfs.
- The GUI's *Apply to GRUB* runs both steps in one job and one progress dialog, GRUB first.

## 1b. Process (maintainer: work in PRs, nothing is broken until everything is done)

- **Repos:** `LucaCraft89/material-plymouth` and `LucaCraft89/material-boot-core` exist and are attached; each got one bootstrap commit (licence and readme) on `main`. `material-boot-core` stays empty until phase 8.
- **material-grub:** integration branch `release/0.8.0` (from `main` at 0.7.1; the name is from before the version decision of row 18, the release is **1.0.0**). One PR per phase, each into `release/0.8.0`, each with green CI. A single final PR `release/0.8.0` to `main` when the whole thing works. `main` does not change before that.
- **material-plymouth:** everything after the bootstrap commit goes through PRs into `main`, green CI each.
- **Inert until installed:** the material-grub changes are additive. New conf keys have defaults, `material-grub plymouth` only reports that the plugin is not installed, the GUI page is hidden without the plugin, and the theme package never depends on the plugin.
- **No release until both are done:** no version bump, tag or published package before the pair is verified (tiers 1 to 4 of section 10, plus the hardware list). They are released together.
- **Core order (opinion, agreed):** Plymouth first; the adapter is written as the future core API, and the extraction to `material-boot-core` is phase 8, again through PRs.
- **The assistant opens PRs and never merges them.** PRs use the repo's template, say what was not verified, and the maintainer merges.

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

1. **Done in Phase 1 (PR #15):** `install/bin/mgrub.py` `CONF_DEFAULTS`/`CONF_CHOICES` for the three keys (so `load_conf`, `write_conf`, `material-grub conf` and `doctor` handle them), the sample `material-grub.conf`, and `mgpresets.CONF_KEYS`. `gui/mgstate.CONF_KEYS`, `gui/mghelper.CONF_KEYS` and the TUI answers are **deliberately left for Phase 5**, so the GUI behaves exactly as before until its Plymouth page exists.
2. **Done in Phase 1 (PR #15):** `install/bin/mgplugins.py` and `cmd_cli.py`: a generic plugin registry (one manifest per part in `/usr/share/material-boot/plugins.d/`, `$MATERIAL_PLUGIN_PATH` for tests) instead of a Plymouth-specific lookup. A part gets `material-grub <name> ...`, menu entries and lines in `help`, `version` and `doctor`; a missing, broken or incompatible (`core_api`) part is reported, never fatal. Contract in `docs/plugins.md`. No new command is installed.
3. `install/bin/mgpresets.py`: `CONF_KEYS` gains the three Plymouth keys (presets carry the Plymouth look). `install/systemd/material-grub.path`/service also run `material-grub plymouth apply --if-changed` when the plugin is installed.
4. `gui/mghelper.py`: a new fixed verb `plymouth` (`apply`, `remove`) that validates its input and calls `material-grub plymouth ...`; the polkit policy is unchanged (same helper).
5. GUI: a **Plymouth** page, visible only when the plugin is installed: on/off, bar mode, motion level, still preview of boot, password and shutdown screens (drawn by the real renderer through a new `/api/plymouth/preview`), and an animated browser preview that plays the real assets with the same motion model (reusing `WavyProgress`). Style, scheme, colours and entries stay on their existing pages and are shared. Apply uses the existing progress dialog and event stream.
6. Docs, CHANGELOG, `docs/gui.md`, `docs/how-it-works.md` (the table "Not possible in GRUB" gets a pointer: the wavy bar and animation now exist, in Plymouth), CI.
7. The material-grub package never depends on, recommends or installs material-plymouth (same rule as the GUI package).

## 8. Packaging (material-plymouth repo)

Sources only, rendered on the target like the main package: rpm (`%posttrans`, dracut), deb (`postinst`, initramfs-tools hook), arch (`post_install`, mkinitcpio hook and pacman hook). It requires `material-grub` of a compatible version (checked by `adapter.py` and `doctor`) and the distro's script plugin. `install.sh` for source installs. Same CI shape as material-grub (lint, unit, containers on Fedora/Ubuntu/Debian/Arch/openSUSE).

## 9. Phases (each one a green, reviewable step)

0. **Spike (DONE, see 9a).** One script theme with a rotating cookie, shapes and the wavy bar, run with Plymouth's X11 renderer under Xvfb in this sandbox (Plymouth is installable here; QEMU is not installed and would need adding). Measures: rotation quality and CPU, wave smoothness, asset size. Decides sprite-wave vs frame-wave and the morph frame budget. If the script engine cannot do it well, I stop and report instead of building on it.
1. **Contract and conf** (material-grub; DONE, PR #15): the keys, `plymouth` subcommand dispatch, doctor hooks, tests. No Plymouth needed to test.
1b. **Upgrades and existing installs** (material-grub, section 9c; code DONE in PR #16, stacked on #15): state record, detection, notice, policy, migration steps with backup and rollback, the installer glue (the package scriptlets run the same installer), `doctor` on the same detection, unit and staged-install tests. **Still open from 1b:** the Ventoy version marker and its `doctor` warning, the TUI screen (a plain `Continue? [Y/n]` prompt for now), and the upgrade matrix in Docker and QEMU on every distro (starting from the 0.7.1 release as package and source), which belongs to the CI tiers.
2. **Renderer**: scene assets for the four styles, light and dark, single seed and per-distro keys, BGRT/Tux, pills, password, messages. Golden tests and screenshots, like the GRUB gallery.
3. **Script theme**: animation, bar modes, password prompt, modes (boot, shutdown, update), fallbacks.
4. **Apply/remove** with the safety pattern, per initramfs system, command-line step.
5. **GUI page and preview**, helper verb.
6. **Packaging and CI** in both repos; container tests check the built initramfs lists the theme (`lsinitrd`, `lsinitramfs`, `mkinitcpio -S`), and the dry-run diff.
7. **Boot test** in QEMU/OVMF (GRUB, then Plymouth, then login), screenshots at each handover to check nothing jumps.
8. Phase 2 of decision 3 and decision 17: extract the shared code into the third repo, and build the unified installer and the `material-boot` command (section 9b), in separate PRs.

## 9a. Phase 0 spike results (done; material-plymouth PR #1, `spike/FINDINGS.md`)

Plymouth 24.004.60, X11 renderer under Xvfb, 1920x1080. **Verdict: the script engine can draw the design; the constraint is CPU.**
- Works: crisp `Image.Rotate` (same size out as in), a smooth round-capped wavy bar from per-dot sprites (indeterminate and progress), shape-morph frames (24 frames of 400x400: +260 KiB, about +15 MB RAM, no extra CPU), and the disk-password prompt end to end (bullets, backspace, answer delivered, bar restored). `Image.Crop/Tile/Scale/Text` exist; there is no clock, only a frame counter at about 50 Hz.
- Cost: everything animated every frame about 93% of a core (and about 40 fps instead of 50); shapes and cookie staggered one per frame at a low cadence, wave every 2nd frame: **about 39%**, with a slower cadence about 25%; nothing moving about 8%. Rotating and moving large sprites is what costs.
- Changes to the design from this: (1) the motion model of section 6 runs on a **staggered, low cadence** with a per-resolution budget, and `PLYMOUTH_MOTION=full|calm|off` changes the cadence, not just on/off; (2) wave from per-dot sprites (the cropped strip has flat ends; crop plus two round-cap dots is an optimisation to try); (3) morph frames stay few, within a RAM budget; (4) the password layout must hide or move the pills.
- **Not shown, to be measured in the QEMU tier and on hardware:** real DRM/framebuffer cost, anything above 1080p (expect about 4x the pixels at 2160), smoothness of low-cadence rotation in motion on a real display, other Plymouth versions.

## 9b. End state: one installer, one `material-boot` command (phase 8)

When the shared code moves to `material-boot-core`, the user-facing shape changes with it:
- **Command:** `material-boot` replaces `material-grub` as the one command. `material-boot grub <sub-command>` carries today's `material-grub` sub-commands (`apply`, `doctor`, `preview`, `colour`, `presets`, `overrides`, `conf`, `ventoy`, `update`, `uninstall`, `gui`, ...) and `material-boot plymouth <sub-command>` carries the Plymouth ones (`apply`, `status`, `remove`, `preview`, ...). Commands that are not specific to one part (`doctor` for the whole system, `update`, `version`, `help`, the menu TUI, `gui`) live at the top level and see every installed part.
- **Modular like today:** each part ships its own command module and registers it with the dispatcher (the plugin mechanism that Phase 1 builds for `material-grub plymouth`, so Phase 1 is designed as this registry from the start); a part that is not installed has no sub-command and no menu entry. A new part later (another bootloader, a login screen) is another module, not a change to the core.
- **Unified installer:** one `install.sh` / TUI with options for what to install and what not: GRUB theme, Plymouth theme, optional GUI, Ventoy sticks; each can be chosen or skipped on the command line (`--with plymouth`, `--without grub`, ...) and in the TUI, with the same safety nets, dry-run, immutable handling and `--progress json` event stream. Style, scheme, colour and the other shared choices are asked once and apply to every selected part.
- **Packages:** `material-boot-core` (shared code, the dispatcher, the installer), `material-grub`, `material-plymouth` and the GUI as modules that require the core, plus an optional `material-boot` meta-package that installs the common set. Exact split to be decided in phase 8.
- **Compatibility (proposed, to confirm):** `material-grub` stays as a thin alias of `material-boot grub` for at least one release with a deprecation note, so existing scripts, the kernel and pacman hooks, the path unit, the polkit helper and user muscle memory keep working; `/etc/material-grub.conf` and `/etc/material-grub/` keep their paths (or are migrated with a symlink), because moving user data is the risky part of a rename.
- Until then (phases 1 to 7) the command is `material-grub plymouth ...` as in decision 15; phase 8 renames it, with the old form kept as an alias.
- Phase 8 stays a set of PRs into `release/0.8.0` or a later release branch, never a change to `main` in one piece, with the whole matrix of section 10 re-run on the unified installer (install only grub, only plymouth, both, none of the optional parts; upgrade from 0.7.x; uninstall each part separately).

## 9c. Upgrades and existing installs (maintainer, fourth message)

**Rule: the installer and every package always assume an install may already exist.** They detect it, tell the user what they found, and update it doing their best, keeping the user's settings. Nothing is overwritten or removed silently.

What exists today (recon): `install.sh` simply replaces ("replacing any older version"), removes the old command names, and replaces or appends `--set` conf lines. The rpm `%posttrans`, deb `postinst` and arch `post_upgrade` re-run `install.sh --from-package` on first install and on upgrades. There is no explicit detection, no notice, no record of which parts are installed, and no migration steps; compatibility so far came from defaults and a lenient `load_conf`.

### Detection
- **A state record** `/var/lib/material-grub/state.json` (new, written by every apply): the parts installed with their versions (core, grub theme, Plymouth, GUI), how each was installed (`package`, `source`, `immutable`), the date, the conf schema, and the Ventoy sticks themed (identity and version). Plymouth records what it changed (command-line edit, backups, initramfs images) so it can be undone and upgraded cleanly.
- **Fingerprints for installs that predate it (0.7.x and older):** `/usr/share/material-grub/VERSION`, `/etc/material-grub.conf`, `/etc/material-grub/` (overrides, icons, presets), `/usr/local/bin/material-grub` and the old command names, `/etc/grub.d/05_material`, `15_material_menu`, `90_material_system`, `/usr/libexec/material-grub-postprocess`, the systemd path and service units, the kernel and pacman hooks, `/var/lib/material-grub/` (env, entries, immutable package copy), `/usr/share/material-grub-gui`, the theme directory in `/boot/grub*/themes/material`, and the package manager's own database (`rpm -qf`, `dpkg -S`, `pacman -Qo`) to tell who owns the files.
- **What it concludes:** none; same version; older (upgrade); newer (downgrade); partial or broken (some pieces missing); owned by a package while a source install is requested, or the reverse; a different layout (normal vs immutable); a GUI or Plymouth part whose version does not fit the core. `material-grub doctor` uses the same detection, so the report and the installer never disagree.

### The notice, then the update
- Always a plain notice first, for example: "Found Material GRUB 0.7.1 (source install; GUI 0.7.1; style list; 3 customised entries; no Plymouth). This will update it to 1.0.0 and keep your settings. Backup: /var/backups/material-grub/upgrade-0.7.1-to-1.0.0-<time>."
- Interactive (TUI): the notice is the first screen with Continue, Details and Cancel. `--yes`, a script, `--progress json` (an `existing_install` event) and the packages' scriptlets proceed without asking and write the notice to the install log and journal.
- `--dry-run` prints the same notice plus the list of migration steps it would run and changes nothing.

### Migrations (the "does its best" part)
- A registry of **ordered, idempotent steps** (`mgmigrate`): each has `describe()`, `plan()` (for dry-run), `apply()` and `verify()`, keyed by the version it migrates from. They run inside the guarded pattern already used (backup, apply, validate, roll back, report), and the old install keeps working until the swap.
- **Kept always:** `/etc/material-grub.conf` values, `overrides.json`, icons, presets, the recorded sticks. Conf: new keys are added with their defaults as commented samples, never by replacing the file; renamed keys are rewritten; unknown keys are kept. Overrides and presets migrate through their own `version` fields.
- **Cleaned up:** old command names, stale hooks and units from older layouts, duplicates (never two path units, never two sets of hooks).
- **Package scriptlets** call the same detection and migration, so a `dnf`/`apt`/`pacman` upgrade and a re-run of `install.sh` behave identically. Conf files stay `%config(noreplace)`/conffiles; migration edits them through `write_conf`, so the user's edits survive.

### Awkward cases (proposed behaviour; veto any)
| Case | Proposed |
|---|---|
| Source installer run over a package-owned install | Refuse with an explanation and the right command (`dnf upgrade`, ...). Do not fight the package manager. |
| Package installed over a source install | Adopt it: the package's files replace the source install's, hooks and units are not duplicated, settings are kept, the old `/usr/local` shim is removed. |
| Downgrade (installed is newer) | Refuse unless `--force`, because newer conf keys, presets and overrides may not be understood; say so. (0.7.x ignores unknown conf keys but rejects presets with them.) |
| Partial or broken install | Say what is missing, and repair it as part of the normal install. |
| Ventoy sticks | Cannot be touched while unplugged: the notice lists the sticks that were themed by an older version, and `doctor` warns when it sees one (a version marker file on the stick is added for this). |
| Immutable systems | Same detection and steps, run through the existing finalize/post-process path. |
| A part without its core, or a core/part version skew | Refuse or warn from the compatibility check (`core_api`, section 7), with the update to run. |
| Interrupted upgrade (power loss) | The backup and the "old keeps working until the swap" rule leave either the old or the new complete install; `doctor` detects a half state and the next run repairs it. |

### Where it fits
- **New phase 1b**, right after Phase 1 and before anything that touches the initramfs or the kernel command line: the state record, detection, the notice, the migration registry, the package scriptlet changes, and `doctor` using the same detection. Plymouth (phase 4) then records its changes in the state from its first version, so removal and upgrade of Plymouth are clean from day one.
- **Phase 8 (unified installer):** it detects 0.7.x and 0.8 material-grub installs and adopts them under `material-boot` without moving user data, with `material-grub` kept as an alias (9b).
- **Tests (added to section 10):** an upgrade matrix on every distro in Docker and QEMU: install the previous release (the 0.7.1 tag, both as a package and from source) with a customised conf, overrides, icons and presets, then upgrade to the new build and check that the notice is shown, settings are preserved, nothing is duplicated, a forced failure rolls back, a downgrade is refused, a partial install is repaired, a second run changes nothing, package-to-source and source-to-package switches behave as above, and uninstall after an upgrade leaves nothing behind. Each release keeps the previous release's tarball in CI as the starting point of the next upgrade test.

## 9d. What the distro probe found (material-plymouth CI, run of 2026-11-19, all five passed)

| Distro | Plymouth | Script plugin | `plymouth-set-default-theme` | Initramfs integration | X11 renderer | Python |
|---|---|---|---|---|---|---|
| Fedora 45 | 26.134.222 | `/usr/lib64/plymouth/script.so` (`plymouth-plugin-script`) | yes (`plymouth-scripts`) | dracut 111, `modules.d/45plymouth` | no (separate package) | 3.15 |
| Ubuntu 24.04 | 24.004.60 | `/usr/lib/x86_64-linux-gnu/plymouth/script.so` | **no**, `update-alternatives default.plymouth` | initramfs-tools hook `plymouth` | no (`plymouth-x11`) | 3.12 |
| Debian stable | (stable) | `/usr/lib/x86_64-linux-gnu/plymouth/script.so` | yes | initramfs-tools hook `plymouth` | no (`plymouth-x11`) | 3.13 |
| Arch | 26.134.222 | `/usr/lib/plymouth/script.so` | yes | mkinitcpio `plymouth` hook (install and runtime) | yes | 3.14 |
| openSUSE Tumbleweed | 22.02.122 | `/usr/lib64/plymouth/script.so` (`plymouth-plugin-script`) | yes (`plymouth-scripts`) | dracut 112, `plymouth-dracut` package | no | 3.13 |

What it changes: (1) the theme tooling cannot assume `plymouth-set-default-theme` (Ubuntu needs `update-alternatives` and an `initramfs` rebuild); (2) the script plugin path is found, not hard-coded; (3) the spike was measured on 24.004, while two distros ship 26.x and one 22.02: **the script API and rendering must be checked on all three generations** (the Xvfb tier gets a job per Plymouth generation once there is a theme: Arch and Fedora containers have the X11-capable 26.x packages, openSUSE 22.02); (4) every probed distro's Python is 3.12 or newer, so the 3.8 floor is about RHEL 8 and older, which the probe does not cover (AlmaLinux 8 is in the installer matrix of material-grub already); (5) the CI runner image `ubuntu-latest` is now Ubuntu 26.04: jobs that depend on a Python or Plymouth version are pinned to 24.04.

## 10. Verification and CI (maintainer: test everything in CI, Docker and QEMU, for all distros)

Four tiers. Everything runs in GitHub Actions on every PR (as the GRUB theme's jobs do); nothing needs the maintainer's machine except the hardware list at the end.

**Tier 1: unit and consistency (seconds, no Plymouth needed).**
- The **consistency matrix** of section 1a: for every option on and off (`COOKIE`, `LOGO`, `STYLE` x4, `SCHEME` x2, single/multi seed, entry colour/name/icon by `key`, `class`, `title`, `file:` pictures, a bad overrides file, two installs of one distro), the adapter's `look()` must equal what `cmd_scenes` resolves for that entry, and the rendered Plymouth assets must match the look (palette colours sampled from the PNGs, cookie present or absent, logo present or absent).
- Identity resolution (`os-release` `ID`, `ID_LIKE`, `NAME`, override keys, Tux fallback), scene geometry equals GRUB geometry, asset budget, conf keys, the preset round trip, `--if-changed` hashing, the safety pattern with fault injection.
- material-grub side: the new conf keys, the `plymouth` dispatch, the helper verb validation, the GUI API. Lint (ruff, shellcheck, `node --check`) in both repos.

**Tier 2: Plymouth rendering in Xvfb (no VM).** Plymouth's X11 renderer plays the real theme under Xvfb; screenshots per style, scheme, motion level and mode (boot, password, shutdown, update) at several resolutions, checked against the GRUB renders (positions, colours) and stored as artifacts. Frame sampling proves the animation moves (rotation, wave phase, morph) and that `PLYMOUTH_MOTION=off` does not.

**Tier 3: Docker, all five distros (install and initramfs, no boot).** Fedora, Ubuntu, Debian, Arch and openSUSE containers: install the built package (rpm, deb, pacman) and `material-grub` of the pinned version, install a kernel package so `/lib/modules` exists, run `material-grub plymouth apply`, then check with the distro's own tool that the initramfs lists the theme files and the script plugin (`lsinitrd`, `lsinitramfs`, `lsinitcpio`), that the command-line step produced the expected `GRUB_CMDLINE_LINUX`/`grubby` change, that the backup exists, that **a forced failure restores the previous initramfs**, that `remove` restores everything, and that a second apply with unchanged inputs does nothing (`--if-changed`). Also the dry-run diff, the package install and upgrade, and the missing-script-plugin message.

**Tier 4: QEMU + OVMF, a real boot per distro (KVM on the runner).** For Fedora, Ubuntu, Debian, Arch and openSUSE: boot the distro's official cloud image, with cloud-init installing the CI-built packages, applying the theme, and rebooting. A test-only unit holds `plymouth-quit` for about 20 seconds so the splash can be photographed. Screenshots (QEMU monitor `screendump`) at: the GRUB menu, the handover (the first Plymouth frame against the last GRUB scene, a pixel diff that fails when the hero, title or cookie jump), mid-boot at two instants (the animation moved), the password prompt (an encrypted-root variant on one distro, and `plymouth ask-for-password` on the others), shutdown and reboot, and the login or the text console after Plymouth quits (the system must still boot). Matrix: every distro on its default look, plus the rotating cases so every style, both schemes, single seed, `COOKIE=off`, `LOGO=off`, a per-distro colour override, a `file:` icon and both bar modes are booted on at least two distros; the full cross product runs nightly and on demand, not on every PR.
- A **fallback boot** on every distro: broken theme files, a missing script plugin and a deleted `splash` argument must still boot to a login.
- A **GRUB to Plymouth to login** run on each distro is also the first QEMU boot of the GRUB theme on those distros (today only Fedora's GRUB is booted in QEMU), so it checks the whole chain at once.

**What I can and cannot run myself.** In this sandbox: tiers 1 and 2 (Plymouth installs here), and tier 3 only if a container runtime is available (not confirmed). Tier 4 needs KVM and a few GB of images, so it runs only in GitHub Actions. The workflow itself can only be proven by Actions runs, so I iterate on the branch and trigger runs through `workflow_dispatch`, and report failures honestly; I don't open a PR unless you ask.

**Real hardware (needs the maintainer, as for the GRUB theme):** a real LUKS prompt, proprietary GPU drivers, the GRUB-to-Plymouth mode switch on real firmware and the Plymouth-to-display-manager handover.

## 11. Risks

- **Script-engine limits** (rotation quality, no clipping, CPU on a simple framebuffer): the reason for Phase 0.
- **Bricking the initramfs.** Mitigated by backup, verify, restore, and by never touching the GRUB fallback entries; still the most dangerous step of the project.
- **Kernel command line edits** on BLS (Fedora): use `grubby`/`/etc/kernel/cmdline` rather than editing entries by hand.
- **Arch** needs the `plymouth` hook in `mkinitcpio.conf` placed after `base udev`; the invasive part is detected and shown first, never silent.
- **Handover jumps** if the GRUB `gfxmode` and the native mode differ (stretching) or the display manager sets its own mode.
- **Two repos drift** until the shared library exists: `adapter.py` and a version check are the guard; a CI job installs both at pinned versions.
- **Asset size** of morph frames inside every initramfs.
- **Distro differences in Plymouth packaging** (measured, see 9d): the Plymouth version ranges from 22.02 (openSUSE Tumbleweed) over 24.004 (Ubuntu 24.04) to 26.134 (Arch, Fedora 45); the script plugin sits in different directories; Ubuntu has no `plymouth-set-default-theme` (it uses `update-alternatives`) while Debian stable, Arch, Fedora and openSUSE have it; Fedora and openSUSE integrate through dracut, Debian and Ubuntu through initramfs-tools, Arch through mkinitcpio hooks. Each is handled per distro and tested in containers and QEMU.

## 12. Before Phase 0 (needed from the maintainer)

1. **Create the repos** (empty, no README, MIT licence, public, and let the Claude GitHub App access them, same as for material-grub):
   - `LucaCraft89/material-plymouth` is needed **now**.
   - `LucaCraft89/material-boot-core` is needed only for phase 8 (the shared library, decision 3). You can create it at the same time or later; I won't touch it before you say so.
   Tell me when they exist and I attach them with `add_repo` (with push access).
2. Approve this plan, including the three proposed behaviours marked "Proposed"/"ignored" in 1a (`COUNTDOWN`, `HINTS`, `RAW_NAME` do nothing in Plymouth; `hidden` does not hide Plymouth; unambiguous `class`/`title` rules apply).
3. Permission for the Phase 0 spike (installs `plymouth` and its script plugin in this sandbox only).
4. Open question: immutable/ostree systems (Silverblue, Bazzite) after the first release, or never.
5. For phase 8, to confirm when we get there (not now): keep `material-grub` as an alias for one release or longer; keep the `/etc/material-grub*` paths; whether the GUI becomes `material-boot gui` with one page per part (assumed yes).

## 13. Status and handoff (2026-11-24)

What exists, what was and was not verified, and what is next. Written for whoever continues (a fresh agent has none of the chat). The rules did not change: work only through PRs, **never merge** (the maintainer does), ask before anything unclear, state plainly what was and was not verified.

### Versions (decision 18)
The three repositories start level at **1.0.0**. material-grub's integration branch is still called `release/0.8.0` (rename it on GitHub; open PRs follow). The migration steps of this release are "since 1.0.0"; the packages need `material-grub >= 1.0.0`. `material-boot-core` is empty: its first commit starts at 1.0.0 (an empty repository has no branch to open a PR against: ask the maintainer how to seed it).

### Open PRs (none merged by me; `release/0.8.0` is the integration branch of material-grub)
**material-grub:** #14 this plan; #15 phase 1 plugin registry and conf keys (`feat/plymouth-contract`); #16 phase 1b upgrade detection, stacked on #15; #19 phase 5 GUI Boot splash page, stacked on #15; #18 documentation screenshots use the penguin, not the build machine's logo (the 79 committed pictures still show a Dell logo until a follow-up regenerates them); #20 version 1.0.0. **#17 (the theme drawn in a corner on screens with no built-in bundle) is merged into `release/0.8.0`** at the maintainer's request; it is **not verified on hardware** (an Asus laptop, about 1366x768, and a Ventoy PC: `git checkout fix/resolution-mismatch`, `sudo ./install.sh`, reboot, `material-grub doctor`).
**material-plymouth** (a chain, each stacked on the one before): #2 CI, #3 identity and layers, #4 theme/script/wavy bar/prompt/messages, #5 apply and remove with rollback, #6 tier 3 (real initramfs per distro), #7 QEMU boot (Fedora), #8 the boot on five distros, #9 the GRUB to Plymouth hand-over, #10 `plymouth preview` (for the GUI), #11 packaging (rpm, deb, Arch). #1 is the spike.
**Merge order (maintainer):** material-plymouth #2 to #11 in order; material-grub #15, then #16, #19, #18, #20, #14. After #15 merges, change `MATERIAL_GRUB_REF`'s default in material-plymouth's `ci.yml` from `feat/plymouth-contract` to the integration branch.
**Not yet run on GitHub:** the CI jobs of material-plymouth #6 to #11 and of material-grub #17 to #20. Expect the first runs to need small fixes (KVM setup step, registry image names, the `ovmf` and `grub-efi-amd64-bin` packages on the runner). CI loop: push, wait about nine minutes, read the run with the GitHub tools.

### What was verified, and how
- **Tier 3** (material-plymouth #6): `plymouth apply` and `remove` against a real dracut, initramfs-tools and mkinitcpio on Fedora, Ubuntu, Debian, Arch and openSUSE: the theme, script plugin and pictures are in the image, `--if-changed` rebuilds nothing, a failing tool and a tool writing broken images both roll back byte-identically. All pass locally.
- **QEMU** (#7, #8, #9): the real kernel and initramfs of each distro, booted in QEMU (software emulation here, KVM on GitHub): the splash draws and animates, the disk-password prompt takes the typed password, shutdown mode shows its message, plymouthd stays up, and every frame is the theme (not a text screen). Plymouth 22.02 (openSUSE), 24.004 (Debian, Ubuntu), 26.134 (Fedora, Arch). **The hand-over:** GRUB under UEFI (OVMF) with material-grub's own theme, then Plymouth, same resolution and the same background and card colours.
- **GUI** (#19): 8 new server tests, a Chromium end-to-end section, and a manual run with the real plugin.
- **Packages** (#11): built and exercised in Fedora, Debian and Arch containers: installing changes nothing about how the system boots; upgrade re-applies only a theme that was applied before; removal takes the theme out first.

### Findings worth knowing (all fixed, with tests)
- **Plymouth 26's script plugin crashes plymouthd when the text-label plugin is missing from the initramfs** (it dereferences a NULL console viewer), for any script theme. `apply` now refuses without the plugin and checks each image holds it.
- **Ubuntu 24.04 under UEFI showed the scene only inside its sprites' rectangles, on black.** The script now re-sets the background colour once a second for twenty seconds, which repaints the whole screen. The cause is not pinned down; this is a workaround (see material-plymouth #9).
- With `update-alternatives`, a failed second apply used to leave a distro default theme behind while the image still held ours.
- `dracut --regenerate-all` can exit 0 while writing nothing: apply verifies the images, not the exit code.
- A test that only checks "not blank, and it changes" passes on a crash dump or an emergency shell: the checks look at the process and at the colours.

### Not verified (be honest about these)
Real hardware of any kind (the display here is QEMU's `bochs` DRM device; the EFI framebuffer handing over to `i915` or `amdgpu` is the part most likely to differ); a real root file system; Secure Boot; the pkexec path and a real initramfs rebuild started from the GUI; installing next to a real material-grub package (none exists until 1.0.0 is released); the CPU cost of the new once-a-second repaint with `PLYMOUTH_MOTION=off` (the Xvfb job measures `off`, `calm` and `full`); only Plymouth 24.004 was ever played in Xvfb (Fedora, openSUSE and Arch ship no X11 renderer, so that tier cannot cover other generations: the QEMU boots do).

### Next (suggested order)
1. **Phase 8** (the maintainer approved it, with a fresh agent): extract the shared code into `material-boot-core` (an adapter is in place in material-plymouth's `adapter.py`, the one place it reaches into material-grub) and build the unified installer and the `material-boot` command (section 9b: `material-boot grub|plymouth ...`, `material-grub` kept as an alias, `/etc/material-grub*` paths kept). Separate PRs, never one change to `main`. Ask the maintainer about the shape before building: this is the big architectural step.
2. The systemd path and service units that run `plymouth apply --if-changed` when the part is installed (item 3 of section 7); an animated preview in the GUI (the plan promises one; #19 has stills).
3. After the maintainer confirms #17 on hardware: scene sets of their own for 4:3 and 5:4 screens (today squeezed 16:10 scenes). If gray remains, ask for the `material-grub doctor` output.
4. A follow-up PR that regenerates `docs/screenshots` with the penguin (after #18 merges); a `--logo penguin` option for screenshots made on any machine.
5. Smaller: the light scheme in the QEMU tests, bump `actions/checkout` and `upload-artifact` (the Node 20 warning), the Ventoy version marker and its `doctor` warning, the upgrade matrix on every distro, multiple displays, immutable systems (ask first). material-plymouth branch `ci/xvfb-per-generation` holds an unfinished per-distro Xvfb script (no PR: it cannot work where there is no X11 renderer).

### Working here (the sandbox)
- Docker is installed but its daemon does not start by itself: `dockerd --iptables=false --bridge=none &`; pull from `mirror.gcr.io` (Docker Hub rate-limits); containers need `--network host` and the proxy variables, and the sandbox CA (`/root/.ccr/ca-bundle.crt`) added to their trust store. There is no KVM: QEMU runs in software emulation (about a minute per boot) and `qemu-system-x86_64`, OVMF and `grub-mkimage` are installed.
- **Run the GUI tests and the end-to-end as a normal user** (`runuser -u nobody`): as root the privileged helper ignores its scratch root and writes the real `/etc` (I did that once by mistake and restored it from the helper's backup). Never run `rm -rf` on a shell variable (the safety check blocks it).
- A built material-grub with the plugin API is needed for material-plymouth's tests: a worktree of `feat/plymouth-contract` with `python scripts/package.py --res 1920x1080,1280x720` (needs `apt grub-common librsvg2-bin`), then `MATERIAL_GRUB=<that path>`.
- The GitHub tools are deferred: load them with ToolSearch (`mcp__github__create_pull_request`, `pull_request_read`, `actions_list`, `get_job_logs`, `merge_pull_request` is not to be used).

## 14. Phase 8 decisions (maintainer, 2026-11-24) and progress

Proposal answered; the full shape is in `docs/architecture.md` of material-boot-core.
- **Command:** `material-boot <module> [command]` with module = `core | grub | plymouth`. The shared settings and tools (`colour`, `presets`, `overrides`, `conf`, `doctor`, `update`, ...) are under `core`. Only `help`, `version` and the menu are top-level. (My opinion, for the record: top-level shared commands would read better to users; the maintainer chose `core` for uniformity. Shortcuts can be added later without breaking anything.)
- **Alias:** `material-grub X` behaves exactly as today (`plymouth` included); `material-grub apply` stays GRUB-only; hooks and units keep calling it in 1.0.0; the deprecation note only in `help`, `version`, `doctor` and the menu.
- **Distribution:** one bundle tarball built by the core's release CI from the three tagged repositories. **Packages:** core uses new paths (no file changes owner); meta-package = core + grub, not Plymouth; `/etc/material-grub*` unchanged, no symlink.
- **Core repo:** it was not empty (bootstrap commit on `main`), so no seeding; PRs go against `main`.
- **Timing:** C1 and C2 now with the modules the open PRs do not touch; `mgrub`, `mgplugins`, `mgdetect` move only after material-grub #15 and #16 merge.
- **Rule for every move:** render hashes (styles x schemes x seeds x resolutions, plus the Plymouth layers) are snapshotted first and must be reproduced byte for byte.
- **Progress:** material-boot-core #1 (C1 skeleton, 1.0.0, CI, architecture) open. Next: the render-hash snapshot, then C2.
- **Plugin API 2 (material-boot-core #6, maintainer confirmed):** the installer chooses parts through `install.default` plus `install.needs` in each part's manifest (no fixed profiles); the reserved words are `core`, `help`, `version`, `menu`. Plymouth needs only the core; the GUI needs `grub`. The hook arguments stay provisional until the installer (C5) exists.
- **Core PRs so far (all open, none merged, stacked in this order):** #1 skeleton 1.0.0, #2 render snapshot (golden hashes of 36 cases), #3 pure modules (overrides, seeds, palette; Python floor 3.9), #4 renderer (scenes, custom, bgrt_logo; gated by `snapshot.py --core`), #5 catalog and data build (byte-identical to material-grub's), #6 plugin API 2.
- **Found on the way:** the vendored `materialyoucolor` does not import on Python 3.8, while `installer.py` still says the installed tools run on "3.8+" (to fix in G1). The snapshot does not draw `render_list_fallback`, Ventoy scenes, GUI previews, other aspect ratios or other resolutions: cases to add before G1. Plymouth has no layer snapshot yet (needed before P1).
- **Deferred to the end (maintainer): animated previews.** The material-plymouth README and the material-grub gallery (`docs/gallery.md`, a Plymouth section) should show rendered GIFs of the animations (the wavy bar, the rotating and morphing shapes, the cookie, the hero pulse), per style. Today neither has any: the Plymouth README has only a CI badge, the gallery has QEMU stills, and `plymouth preview` writes stills. Notes for whoever does it: the frames can come from the real renderer with the real motion model (the same one the GUI's animated preview is meant to play), or from QEMU captures of a real boot (the boot tests already grab frames); the former is reproducible and independent of the machine. Keep each file small (a README loads them all): a short loop, a modest size and frame rate; a GIF has 256 colours, so smooth gradients may band (to check on the real frames; the alternative is an APNG or a short video linked from the page). Generated by a script in the repository and regenerated in CI like `docs/screenshots`, never edited by hand; show the penguin, not the build machine's logo (see #18).
- **Merged by me, with the maintainer's explicit permission ("go ahead and merge when green", scope: these two only) on 2026-11-24:** material-grub **#15** (phase 1, `4fc4431`) and **#16** (phase 1b, `588f909`) into `release/0.8.0`. #15 first had to be brought up to date (it conflicted with `release/0.8.0` after #17 merged; only `CHANGELOG.md` conflicted, resolved by keeping both blocks), and CI was rerun on the real base: 39 of 40 jobs green and 1 skipped (the manual gallery job), for each. #16's earlier red job (Ventoy features in QEMU, gui: the stick's entries had not appeared within 5 seconds) passed on the rerun; it was a timing flake, not a regression. The standing rule ("never merge") is otherwise unchanged: nothing else was merged.
- **Still open after that:** material-grub #14 (this plan), #18, #19 (stacked on the now merged `feat/plymouth-contract`: retarget it to `release/0.8.0` before merging), #20; the material-plymouth chain #2 to #11 (its `ci.yml` still defaults `MATERIAL_GRUB_REF` to `feat/plymouth-contract`: change it to `release/0.8.0`); material-boot-core #1 to #6.

