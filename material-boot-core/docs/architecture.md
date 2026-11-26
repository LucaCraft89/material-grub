# Architecture: one command, parts that plug into a core

This is the agreed shape of phase 8 (decisions of the maintainer; the long form is `docs/plans/plymouth.md` in material-grub, sections 9b, 9c and 13). Nothing below is built yet except the skeleton: each section says which pull request builds it.

## Command

```
material-boot <module> [command]      module = core | grub | plymouth | (any future part)
material-boot help | version          the only top-level words (they must work with nothing installed), plus the menu when run alone
```

- `material-boot core colour|presets|overrides|conf|doctor|update|uninstall|gui|apply ...`: the settings and tools that belong to the whole system. `core` is itself a registered module, so the dispatcher has no special case.
- `material-boot grub apply|preview|ventoy|...`: GRUB only.
- `material-boot plymouth apply|status|remove|preview|...`: Plymouth only.
- A part that is not installed has no module, no menu entry and no line in `help`.
- **How it runs:** `bin/material-boot` (a POSIX shell shim; the packages install it as `/usr/bin/material-boot`) puts the library on `PYTHONPATH` (`$MATERIAL_LIB`, else `/usr/share/material-boot/lib`, else the checkout) and runs `python -m material_boot`; `/var/lib/material-grub/env` may name another Python (`MATERIAL_PY`) for systems whose `python3` is too old. The code is `material_boot/cli.py` (the dispatcher and the helpers a part receives), `commands.py` (the `core` module) and `menu.py`.
- **`core` today:** `conf`, `colour`, `overrides` (the shared-settings commands of `material-grub`, bodies unchanged), `apply` (the `apply` of every installed part, one failing does not stop the others), `doctor` (the core, every part, and each part's `hook_doctor`) and `parts`. `presets` (needs `mgpresets`), `update`, `uninstall` and `gui` come with the code they depend on.
- **The alias is not a mapping, it is the old front end.** `material-grub X` keeps working because material-grub keeps its existing `cmd_cli.py` as the legacy front end (same commands, same messages, same exit codes), rebuilt on the core's modules in G1 and given the core's plugin registry for `material-grub plymouth ...` in G2. That is the only way to guarantee "exactly as today" for the hooks, the path unit and the polkit helper. `material-boot` is the new front door; the two share the code, not the command table.
- `material-grub` stays as an alias of the old behaviour: `material-grub X` does what it does today, `plymouth` included, and `material-grub apply` stays GRUB-only (a hook must never rebuild an initramfs by surprise). The deprecation note shows only in `help`, `version`, `doctor` and the menu, never in hook or journal output. Hooks, units and the polkit helper keep calling the alias in 1.0.0.

## What lives here

Shared by every part: the conf, rules and title parsing; `overrides.json`, presets, palettes, seeds and the per-entry customisation (`mgcustom`); the renderer primitives, palettes, glyphs and fonts; the distro data (`palettes.json`, `classes.json`, the catalog rules, glyphs); the guarded backup / apply / validate / roll-back pattern; the state record, install detection and migrations; the module registry; the dispatcher and menu; the installer framework.

**The renderer moves whole** (`scenes`, `custom`, `bgrt_logo`): material-plymouth calls most of it (`hero`, `draw_list`, `draw_side_hero`, `draw_cookie`, `list_label`, ...), so a cut between "primitives" and "GRUB layouts" would be arbitrary. The core therefore still carries some GRUB-flavoured drawing (the rail, the key hints); separating it is a later cleanup, under the same pixel gate.

**Found while moving (C3): `mgsafe` is not shared code.** It validates `grub.cfg` (the script scanner, `grub-script-check`, "entries were lost"); Plymouth never calls it and has its own rollback, and `mgmigrate` has a third. So it stays in material-grub, and a common transaction layer for the unified installer would be a new design (proposed separately), not a move. `mgdetect` is the same kind of case: its state record is generic, its file fingerprints are GRUB's.

Stays in the parts: GRUB scene layouts, resolutions, BLS handling, the `grub.d` scripts, units and hooks, Ventoy (material-grub); the initramfs, kernel command line and script theme (material-plymouth).

## Packages and paths

| Package | Owns | Requires |
|---|---|---|
| `material-boot-core` | `/usr/share/material-boot/{lib/material_boot,data,plugins.d}`, the `material-boot` shim | python |
| `material-grub` | `/usr/share/material-grub` (as today, minus what moved), the `material-grub` alias | core, same major |
| `material-plymouth` | `/usr/share/material-plymouth` | core, same major (no longer material-grub) |
| `material-grub-gui` | as today | core |
| `material-boot` (meta) | nothing | core and grub; **not** Plymouth, which rebuilds the initramfs and is always an explicit choice |

- **Python 3.9 is the floor** (the same as material-grub's packages). The vendored colour science does not import on 3.8, which CI found; material-grub's installer still says "3.8+" for the installed tools, which is therefore wrong and is tracked for G1.
- The core uses **new paths**, so no file changes owner between packages (that is what breaks rpm, dpkg and pacman upgrades).
- The core is a private directory on `sys.path`, not `site-packages`, like the tools today; the immutable-system copy in `/var/lib/material-grub/pkg` carries it too.
- **User data keeps its names and places**: `/etc/material-grub.conf`, `/etc/material-grub/`, `/var/lib/material-grub/`. No symlink (it adds failure modes for nothing); the names are historical.

## Parts and the plugin API (`CORE_API = 2`)

The contract is [plugins.md](plugins.md); the code is `material_boot/plugins.py`.

GRUB registers exactly like Plymouth, so Plymouth can be installed without GRUB. A manifest in `plugins.d/` lists the part's commands, menu entries, installer options and hooks (`detect`, `plan`, `install`, `uninstall`, `migrate`, `verify`). API 1 was the first draft inside material-grub and was never released, so nothing needs a compatibility layer. A part with another `core_api` is not run; `doctor` says which side to update.

## The installer

One installer with `--with plymouth`, `--without grub`, ..., the same choices in the TUI, and the safety nets of today: dry-run, immutable handling, `--progress json`, the notice for an existing install, shared questions asked once. Each part provides its steps through the hooks above. Distribution: one **bundle tarball** built by this repository's release CI from the three tagged repositories (one download, offline, checksummed). Packages stay one per repository.

## Existing installs

The installer and the packages always assume an install may exist (plan 9c). The 0.7.x monolith becomes core + grub through one ordered, idempotent migration "since 1.0.0": add the core, turn the old command into the alias, delete the module copies that moved (two copies of a module on `sys.path` would run the old code silently; `doctor` checks for it). A package-owned core makes a source install of a part refuse with the right command; mixed ownership of one part is refused.

## Verification rule for the moves

Before any module moves, a snapshot of full renders (styles x schemes x seeds x resolutions) and of the Plymouth layers is taken from the current code. Every pull request that moves code must reproduce it byte for byte: `tests/snapshot/snapshot.py --core` swaps the moved modules for shims onto this package (`MOVED` and `PARTIAL` in that file grow with each move: a partly moved module such as `mgrub` is rebuilt without the moved definitions, which are imported from here), and `tests/test_provenance.py` checks that every moved definition equals the original, statement for statement. The strongest gate is `tests/gate/grub_suites.py`: it runs **material-grub's own unit suites** (the 50 upgrade tests included) on a copy of its checkout whose moved modules come from here, next to the same suites on the unmodified copy, and fails when a suite that passes on the original fails on the core's. `tests/gate/moves.py` is the one table all of these read and compares with `golden.json`.

## Pull requests

Core into `main`: C1 this skeleton; C2 the pure modules, their tests and the data; C3 guarded, state, detect, migrate, registry; C4 dispatcher, `material-boot` and the menu; C5 installer framework, bundle builder, packages. Then material-grub (G1 to G4) and material-plymouth (P1 to P3), and a final one for the unified installer and the whole test matrix. Never one change to `main`.
