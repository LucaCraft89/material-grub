# Optional parts (plugins)

Material GRUB is one **part** of Material Boot, next to [material-plymouth](https://github.com/LucaCraft89/material-plymouth) (the boot splash that continues this theme) and whatever comes next. The parts share [material-boot-core](https://github.com/LucaCraft89/material-boot-core): the palettes, the scene renderer, the settings, the overrides, the presets, the state record, the installer and the plugin loader.

When a part is installed it adds a sub-command (`material-boot plymouth ...`, and `material-grub plymouth ...` through this command), a line in `help`, `version` and `doctor`, and entries in the menu. A part that is not installed has none of them.

**The contract is the core's: plugin API 2.** It is documented once, where the code is: [material-boot-core/docs/plugins.md](https://github.com/LucaCraft89/material-boot-core/blob/main/docs/plugins.md) (the manifest, the hooks `detect`, `plan`, `install`, `verify`, `uninstall`, `migrate`, `doctor`, the `core` object and the context a hook gets) and [docs/installer.md](https://github.com/LucaCraft89/material-boot-core/blob/main/docs/installer.md) (how `material-boot core install` runs the parts).

## How Material GRUB is a part

- `material-boot-part.json` (the manifest) and `install/part_grub.py` (the entry file and the hooks). The hooks run this repository's own installer, `install/installer.py` (the program `sudo ./install.sh` runs), so the two ways of installing do the same thing: a test installs with both and compares every file. Design and findings: [plans/g2-grub-part.md](plans/g2-grub-part.md).
- `install.sh` puts the manifest in `/usr/share/material-boot/plugins.d/grub.json` and the entry next to the tools; the packages ship the manifest as one of their own files.
- This front end, `material-grub`, keeps its own commands, messages and exit codes (the polkit helper, the path unit and the GUI parse them); for the parts of other packages it uses the core's loader, and its own command names stay reserved: a part cannot take `apply`, `doctor` or any other built-in name.

## Writing a part

Read the core's `docs/plugins.md`, put a `material-boot-part.json` at the root of the repository, give the entry file `main(argv, core)` and the hooks, and test it with `MATERIAL_PLUGIN_PATH` pointing at a directory that holds the manifest. material-plymouth is the worked example (its hooks are tested on fake machines and through the real `material-boot core install`).
