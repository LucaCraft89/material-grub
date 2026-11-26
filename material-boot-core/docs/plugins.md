# Parts and the plugin API (API 2)

Material Boot is a core plus **parts**: material-grub, material-plymouth, the GUI, and whatever comes next (another bootloader, a login screen). A part lives in its own package and repository. The core finds it through **one manifest file**, runs its commands as `material-boot <part> ...`, and hands its steps to the unified installer. A part that is not installed has no manifest, so it has no module, no menu entry, no line in `help` or `doctor`.

The code is `material_boot/plugins.py` (tested by `tests/test_plugins.py`). This page is what a part author needs to know.

> **Status.** The manifest, discovery, dependency resolution, loading, running and the `core` object are fixed by tested code. The **hook arguments** (`ctx` and the return values, below) are the contract the installer will be built against; they are provisional until that installer exists (C5) and may still change before 1.0.0 is released. API 1 was a first draft inside material-grub that was never released: there is no compatibility layer.

## The manifest

One JSON file per part in a plugin directory: `/usr/share/material-boot/plugins.d/` or `/usr/local/share/material-boot/plugins.d/` (`$MATERIAL_PLUGIN_PATH`, `os.pathsep`-separated, replaces both: tests and checkouts). The first manifest of a name wins; the others are reported by `doctor` as shadowed.

```json
{
  "manifest": 2,
  "name": "plymouth",
  "title": "Plymouth boot splash",
  "version": "1.0.0",
  "summary": "boot splash that continues the GRUB theme",
  "core_api": 2,
  "core_min": "1.0.0",
  "entry": "/usr/share/material-plymouth/bin/mgplugin.py",
  "commands": {"apply": "render the theme and rebuild the initramfs", "status": "what is installed"},
  "menu": [["Apply the Plymouth theme", "Render it and rebuild the initramfs", ["plymouth", "apply"]]],
  "conf": ["PLYMOUTH", "PLYMOUTH_BAR", "PLYMOUTH_MOTION"],
  "install": {"default": false, "needs": ["grub"]},
  "hooks": ["detect", "plan", "install", "uninstall", "migrate", "verify", "doctor"]
}
```

| Key | Required | Meaning |
|---|---|---|
| `manifest` | yes | `2`. Another number makes the part unusable, with a sentence saying so. |
| `name` | yes | The module: `material-boot <name> ...`. 2 to 20 characters: a letter, then lowercase letters, digits or `-`. `core`, `help`, `version` and `menu` are the core's own and cannot be taken. |
| `core_api` | yes | Must equal the core's `CORE_API` (2). A part for another API is **not run**; the message says "update whichever of the two is older". The number changes only for a breaking change; new optional manifest keys do not change it, and unknown keys are ignored. |
| `core_min` | no | The oldest `material-boot-core` the part works with (`1.0.0`). An older core makes the part unusable: "update the core". |
| `entry` | yes | Path of a Python file (see below), absolute in an installed manifest, **or relative to the manifest's directory** (a bundle's manifest cannot know where it will be unpacked). If it is missing, the part is reported as half-removed. |
| `title`, `version`, `summary` | no | For `help`, `version` and `doctor`. |
| `commands` | no | `{command: one line}`. For `help`, the menu and error messages ("unknown command, try: ..."); the part still parses its own arguments. |
| `menu` | no | `[title, description, [words]]` entries of the `material-boot` menu. The first word must be the part's own name: a part cannot add a menu entry that runs another part (it is ignored, with a warning). |
| `conf` | no | The keys of `/etc/material-grub.conf` the part owns, so `core conf`, presets and the GUI can show and validate them. The file keeps its historical name and path. |
| `install` | no | For the unified installer ([installer.md](installer.md)): `default` (installed on a fresh system when the user chooses nothing; false for everything that rebuilds the initramfs), `needs` (other parts that must be usable; `core` is implied), `package` (the package that provides the part, for the notice and the "update it with your package manager" command), `layouts` (`normal`, `immutable`: the layouts it supports; the installer refuses the others with a sentence) and `options` (`[{name, takes: "flag"|"value", summary}]`: the part's own install options, accepted as `--<part>-<name>`, and as `--<name>` when only one chosen part declares it). |
| `hooks` | no | Which of the optional installer and `doctor` hooks the entry file defines. |

Problems never take the core down: a broken, incompatible or unsatisfied part is a sentence in `doctor` and `help`; the rest keeps working. Things that were ignored (a malformed command, a menu entry for another part, an unknown hook) are warnings.

### Dependencies

`install.needs` names other parts. A part whose need is missing or unusable is itself unusable, and the chain is followed (`gui` needs `grub`, which is broken, so `gui` is reported as "needs the grub part, which cannot be used"). **material-plymouth needs nothing but the core**: it installs and runs without material-grub. The GUI needs `grub`.

## The entry file

A Python file that the core imports (its own directory is on `sys.path` while it loads, so its modules can sit next to it). It defines:

```python
def main(argv, core):
    """`material-boot <name> <argv...>`. Return the exit status (None counts as 0)."""


def hook_install(ctx): ...  # one function per hook the manifest lists, named hook_<name>
```

`main` parses its own arguments. An uncaught exception is reported as "the <name> part failed" and exits 1; `SystemExit` codes are honoured; Ctrl-C exits 130. A manifest that lists a hook the file does not define is a load error, so a half-updated package is caught early.

### What a part gets: `core`

| | |
|---|---|
| `core.api`, `core.version` | the API number and the core's version |
| `core.data` | the shared data directory (`palettes.json`, `classes.json`, `glyphs/`, `fonts/`, ...) |
| `core.lib` | the directory that holds the `material_boot` package; put it on `sys.path` to import the shared modules (`overrides`, `palette`, `scenes`, `custom`, ...) |
| `core.say(text)` | print a line the way the core does |
| `core.run(cmd)` | run a command |
| `core.elevate(argv, paths)` | re-run through sudo when one of the paths is not writable |
| `core.conf_path()`, `core.state_dir()` | `/etc/material-grub.conf` and `/var/lib/material-grub` (`$MATERIAL_CONF`, `$MATERIAL_STATE_DIR` move them) |
| `core.parts` | the names of the usable parts, so a part can tell whether another is installed |

## Hooks (provisional)

Called by the unified installer, `doctor` and the upgrade machinery, each as `hook_<name>(ctx)`. A hook that crashes is a failed step (reported and rolled back), never an exception that takes the installer down; a part without a hook is simply skipped.

`ctx` carries `core`, `root` (a staged tree for tests and packaging; empty for the real system), `dry_run`, `yes`, `progress(event)` (the `--progress json` stream), `options` (the part's own installer choices), `conf`, `backup_dir`, `previous` (what the state record says about this part, or `None`) and `target_version`.

| Hook | Returns |
|---|---|
| `detect` | what is installed: found or not, version, how (`package`, `source`, `immutable`), problems |
| `plan` | sentences for what `install` would change now (the dry-run) |
| `install` | `{"changed": bool, "notes": [...]}`; raises on failure; must be idempotent and leave the old install working until the swap |
| `uninstall` | the same, and must remove only what the part installed |
| `migrate` | results of the part's ordered, idempotent migration steps for an older install |
| `verify` | a list of problems (empty when healthy) |
| `doctor` | `[(level, text)]` lines for the part's section of `material-boot core doctor` |

## Commands

`material-boot <part> [command]`. The core is itself a module: `material-boot core <command>` carries the settings and tools that belong to the whole system. Today: `conf`, `colour`, `overrides`, `apply`, `doctor` and `parts`; `presets`, `update`, `uninstall` and `gui` follow with the code they need. Only `help`, `version` and the menu are top-level; a core command typed at the top level gets a "did you mean `material-boot core ...`" hint.

- **`core apply`** runs the `apply` command of every usable part whose manifest lists one (`commands`), in name order; one failing does not stop the others, and the exit status says so. `--only PART` runs one.
- **`core doctor`** prints the core, every part (and why one cannot be used), then each part's `hook_doctor(ctx)` lines `[(level, text)]`; a level of `fail` or `error`, a part that cannot be used, or a hook that crashes makes the exit status 1.
- **`material-grub X`** is not mapped onto these: it stays as material-grub's own front end with its own commands, messages and exit codes (see `architecture.md`), so the hooks, the path unit and the polkit helper cannot notice the change.

## Testing a part

Put a manifest and an entry file in a temporary directory, set `MATERIAL_PLUGIN_PATH` to it, and run `material-boot <part> ...`; or call `material_boot.plugins.read_manifest`, `discover`, `run` and `call_hook` directly, as `tests/test_plugins.py` does.

## Shipping a part: `material-boot-part.json`

A part's repository keeps its manifest at its root as `material-boot-part.json` (the same file as the one the package installs into `plugins.d`, with `entry` relative to the repository). The bundle builder takes the part's committed files into `parts/<name>/`, checks that the manifest is usable, and copies it to `parts/<name>/manifest.json`, which is where the installer looks for parts that are not installed yet. See [installer.md](installer.md).

