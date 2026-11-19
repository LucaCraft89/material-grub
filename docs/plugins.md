# Optional parts (plugins)

Some parts of Material GRUB live in their own packages and repositories. The first is [material-plymouth](https://github.com/LucaCraft89/material-plymouth), the boot splash that continues this theme. A part is **never required and never installed by this package**: without it nothing changes, and `material-grub` behaves exactly as before.

When a part is installed it adds a sub-command (`material-grub plymouth ...`), a line in `material-grub help`, `version` and `doctor`, and entries in the menu. A part that is not installed has none of these; asking for a known part that is missing says so and exits with status 1.

## The contract (plugin API 1)

A part announces itself by installing **one manifest** in a plugin directory (`/usr/share/material-boot/plugins.d/` or `/usr/local/share/material-boot/plugins.d/`; `$MATERIAL_PLUGIN_PATH` overrides both, for tests and checkouts):

```json
{
  "manifest": 1,
  "name": "plymouth",
  "title": "Plymouth boot splash",
  "version": "0.1.0",
  "core_api": 1,
  "entry": "/usr/share/material-plymouth/bin/mgplugin.py",
  "summary": "boot splash that continues the GRUB theme",
  "menu": [["Apply the Plymouth theme", "Render it and rebuild the initramfs", ["plymouth", "apply"]]]
}
```

- `name` is the sub-command (2 to 20 characters: a letter, then lowercase letters, digits or `-`). A built-in command name is refused.
- `core_api` must equal the plugin API of the installed `material-grub` (`mgplugins.CORE_API`, 1 today). A part written for another API is **not run**; `doctor` and `help` say which of the two to update.
- `entry` is the absolute path of a Python file that defines `main(argv, core) -> int`. `argv` is what follows the part's name on the command line. The part has its own sub-commands and parses them itself, so each part stays as modular as `material-grub` is.
- `core` gives the part what it needs from `material-grub`: `api`, `version`, `pkg` (the package directory), `say(text)`, `run(cmd)`, `elevate(argv, paths)` (re-run through sudo when a path is not writable) and `conf_path()`. The part reads the shared settings through the modules of the installed package (`mgrub`, `mgoverrides`, ...), which is the contract that will move into a shared library later.
- `menu` (optional) adds entries to the `material-grub` menu: `[title, description, [command words]]`.

A broken manifest, a missing entry file or a part that crashes never breaks `material-grub`: it is a warning in `doctor`, an error message for that one command, and everything else keeps working.

## Settings the parts share

The runtime options of a part live in the same `/etc/material-grub.conf` as the theme's, so `material-grub conf`, presets and the GUI see them. Plymouth's three are `PLYMOUTH=on|off`, `PLYMOUTH_BAR=indeterminate|progress` and `PLYMOUTH_MOTION=full|calm|off`; they do nothing until the part is installed. Style, scheme, colours and per-entry overrides are the theme's own and are shared by every part.
