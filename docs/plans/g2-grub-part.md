# G2: material-grub registers as a part of the unified installer (design, for review)

Docs only: nothing in this file is implemented. It builds on G1 (#21: material-grub imports its shared code from the installed `material-boot-core`) and on the contract in the core's `docs/plugins.md` and `docs/installer.md` (API 2). Read those first; this file only says how **GRUB's existing 1,290-line `install/installer.py`** is cut into hooks.

## Goal and the one rule

`material-boot core install --only grub` and `sudo ./install.sh` (today's command) must do **the same thing, byte for byte on the target**. The rule: **the logic moves, it is not rewritten.** `install/installer.py` keeps working as the engine; the part's hooks call it. That keeps the 40 CI jobs (boots in QEMU, packages, the installer on seven distros) meaningful for the unified path, instead of testing a new implementation.

## What ships

1. `material-boot-part.json` at the repository root: name `grub`, `core_api 2`, `core_min 1.0.0`, `entry` `install/part_grub.py`, `commands` (`apply`, `doctor`, the commands the menu lists), `install.default: true`, `install.needs: []`, `install.layouts: ["normal","immutable"]`, `install.package: "material-grub"`, and `install.options` for the GRUB-only options (`res`, `ventoy`, `mode`, `stage-only`, `pkg`, `immutable`, `with-gui`, ...), taken from the argument parser that exists, not invented.
2. `install/part_grub.py`: the hooks, thin.
3. `material-grub` (the command) is **unchanged** (decision 18 earlier: legacy front end, same behaviour).

## Hook by hook

| Hook | Becomes | Moved from | Notes |
|---|---|---|---|
| `detect` | `mgdetect.detect(root, target)` | `Installer.existing_install` (the detection half) | The notice, the policy (no downgrade, no source over package) and the question go to the core's generic versions; GRUB keeps only the detection. |
| `plan` | the dry run | `run_all` `--dry-run` branch (`material-grub-dryrun`) | Returns the sentences; builds in a scratch dir, writes nothing. |
| `install` | everything from `questions`/`dependencies`/`resolution`/`build` to `grub_install` | `run_all`, `build*`, `grub_install`, `ventoy_install`, `install_gui` | Takes the answers from `ctx.options` and the shared look from the conf the core already wrote. `--stage-only` and `--preview` stay options of this hook. |
| `migrate` | `mgmigrate` steps of GRUB | `after_install` | The core's `ConfSamples` is already core-side; GRUB's steps register here. |
| `verify` | the checks `grub_install` already ends with (the `grub.cfg` contains the theme, `grub-script-check`, the guard of `mgsafe`) | `grub_install` tail | Returns problems; no new checks. |
| `uninstall` | `install/uninstall.sh` logic | `uninstall.sh` | Must remove only what GRUB installed and restore the backup of `grub.cfg`/`/etc/default/grub`. |
| `doctor` | `material-grub-doctor` output | `cmd_doctor.py` | Wrapped as `[(level, text)]`. |

The **TUI** (`install/tui.py`) is GRUB's questions. Until the core has `hook_questions` (open point in `installer.md`), it runs inside `hook_install` when a terminal is present and no answers were given, exactly as today.

## Decisions I ask you to confirm

1. **Engine stays; hooks are thin** (above). The alternative, splitting `Installer` into step functions first, is a refactor of 1,290 lines with no behaviour change to show for it; I would only do it where a hook needs a seam (the existing-install half is the one).
2. **Shared look is not asked again by GRUB.** `questions()` asks style/scheme/seed/cookie/logo/hints; when GRUB runs under the unified installer those come from the conf the core wrote, and only GRUB's own questions (resolution, mode, GUI, Ventoy) remain. A plain `sudo ./install.sh` asks everything as today (the legacy engine path is kept and tested).
3. **Two entry points, one engine, both tested.** `install.sh` (legacy) and the hook path each have a staged-root test that installs, upgrades from 0.7.x, and uninstalls, and a test that the resulting file trees are **identical**. That test is the proof of "same thing".
4. **`--progress json`**: the event names are the contract the GUI reads; the part reports through `ctx.progress`, which tags `part: "grub"` (a new field, nothing renamed). The GUI keeps working unmodified.
5. **No `material-boot-part.json` for the GUI yet** (`gui` becomes its own part later, `needs: ["grub"]`); `--with-gui` stays a GRUB option meanwhile.

## Tests (nothing counts that was not made to fail)

- Hooks against a **staged root** (`ctx.root`): every hook with the real GRUB tree, no mocks for GRUB itself; fakes only for `grub-install`/`update-grub` as the installer tests do today.
- The identical-tree test (decision 3) plus **mutation checks**: each hook deliberately broken (skip `verify`, install into the wrong path, leave a file on `uninstall`) must fail a test.
- The existing CI stays as is: QEMU boots, packages, seven distros. Package scriptlets keep calling `install.sh --from-package` until G3 (so G2 changes no package behaviour).
- A snapshot test that `material-boot core parts` lists `grub` usable, and `core doctor` has a GRUB section.

## What G2 does **not** do

Packages requiring `material-boot-core` (G3); the upgrade matrix (G4); Plymouth (P1-P3); immutable systems without a place for the core (still open from G1); changing any user-visible message of `material-grub`.

## Honest unknowns

- I have not read every branch of `Installer` for hidden coupling to `self` state between steps (e.g. `self.found`, `self.imm`); the cut may need small seams, which is why decision 1 says "where a hook needs one".
- The identical-tree test needs a runnable GRUB install tree in CI; the QEMU jobs prove boot, not byte equality. I expect to reuse the existing staged install (`--stage-only`/`--root`) but have not confirmed that it covers `/etc` and `/boot` writes.
- The sudo/elevation and curses paths stay untested here, as they are today.

## Implemented (what differs from the design above)

- `material-boot-part.json` and `install/part_grub.py` exist; hooks: `detect`, `plan`, `install`, `verify`, `uninstall`, `doctor` (no `migrate`: the engine runs GRUB's migration steps itself, in `after_install`).
- The hooks start `install/installer.py` as a child process (so the legacy and the unified entry points cannot drift). It is told it is run by the unified installer through `MATERIAL_BOOT_UNIFIED=1`: it then neither repeats the notice/policy/question nor writes the core's version into the state record (only `parts.grub`).
- Two small additions to the core (material-boot-core #16): `ctx.json` (a json run relays the engine's events through `ctx.progress`) and `record: false` in an install result (a part that only built something, `--grub-stage-only`, is not recorded as installed).
- `--ventoy` takes the stick's mount point as a value here (`--grub-ventoy PATH`); the engine's bare `--ventoy` (ask which stick) is still available through `install.sh`.
- A staged root (`--root`) is supported for `--grub-stage-only` and dry runs only: the engine writes to the real system otherwise, and the hook says so instead of pretending.
- Tested: `tests/test_grub_part.py`. The identical-files test builds the theme with `install.sh`'s engine, through the hook, and through `material-boot core install --only grub` on a staged root: the three trees are byte-identical (checked locally, about 2.5 minutes; skipped where `rsvg-convert` is missing). Verified by deliberately breaking the part and the engine (seven breakages, each fails a test).
- A real install, in a Debian and a Fedora container with a fake /boot (`tests/containers/unified_smoke.sh`, CI job \"Unified installer\"; run locally on both: ALL OK): the core through `material-boot core install`, GRUB with `install.sh` (snapshot of 478 / 1062 files), removed, then GRUB through `material-boot core install --only grub`: **the same files**, `core doctor` and `material-grub doctor` pass, the state record names grub, and the unified uninstall restores `grub.cfg` byte for byte. The test found two real bugs, both fixed here: GRUB read the core's version in the shared state record as its own (a core-only record looked like a newer GRUB), and the hook wrote the shared look's defaults into the config as explicit values where `install.sh` leaves commented samples.
- **Not verified:** the QEMU boot of an install made through the unified installer (the same files as `install.sh`'s, so I expect it to boot, but have not booted it); `--progress json` end to end against the GUI; a real (not container) machine; the package scriptlets (G3); immutable systems.

## G3 (done in the same stack): the packages need the core and call the unified installer

- The three package definitions require `material-boot-core >= 1.0.0` (rpm `Requires`, deb `Depends`, Arch `depends`), ship the part's manifest as their own file (`/usr/share/material-boot/plugins.d/grub.json`, its entry the copy of the sources that has the installer, `/usr/share/material-grub-src/install/part_grub.py`) and call `material-boot core install --from-package --only grub --yes` in the scriptlets (the old `install.sh --from-package` stays as the fallback when the command is missing). `install.sh --no-register` (passed by the engine in package mode) leaves the package's manifest alone; a source install still registers its own.
- `install/uninstall.sh` now forgets only GRUB in the state record (it used to delete the whole file, with the core's entry).
- The package smoke test (`tests/containers/pkg_smoke.sh`) installs the core's package with GRUB's (built by the core's own `build_pkg.sh`), checks that `material-boot core parts` lists grub, that the record names both, that the manifest is the package's, and, at the end, removes GRUB: grub.cfg plain again, manifest gone, the core's entry kept, `material-boot` still works. **Run here on Fedora, Debian and Arch: ALL OK.**
- **Not verified:** an upgrade from a 0.7.x package that did not need the core (the dependency pulls it in; not run); the two packages installed in separate transactions in the opposite order; removal of the core while GRUB is installed (the dependency stops it); COPR/PPA/AUR repositories (no repository exists yet).
