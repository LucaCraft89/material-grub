# The commands (`material-boot grub ...` and the rest of `material-boot`)

Since 1.2.0 there is **one command for the whole of Material Boot: `material-boot`** (the `material-grub` command is gone). The commands of the GRUB part are `material-boot grub ...`; the look (style, colours, presets, per-entry changes) is shared with the other parts and is `material-boot core ...`; the editor is `material-boot ui`. The full reference, with every option and example, is [material-boot-core's commands page](https://github.com/LucaCraft89/material-boot-core/blob/main/docs/commands.md), `material-boot help` and `man material-boot`.

## The GRUB part: `material-boot grub ...`

| Command | What it does |
|---|---|
| `material-boot grub doctor [--json]` | check the installation (`status` is an alias); paste it into a bug report |
| `sudo material-boot grub apply` | regenerate `grub.cfg` and re-apply the theme (also reads `overrides.json`) |
| `material-boot grub preview` | your own boot entries rendered as a web page, nothing is installed |
| `material-boot grub ventoy [STICK] [options]` | theme a Ventoy stick; without `STICK` the mounted one is found ([ventoy.md](ventoy.md)) |
| `sudo material-boot grub uninstall` | remove Material GRUB (your settings in `/etc` stay) |

Commands that write system files ask for root themselves: in a terminal they re-run through `sudo` (your password or fingerprint), otherwise they tell you to run `sudo material-boot grub ...`.

## Where the old words went

| before 1.2.0 | now |
|---|---|
| `material-grub` alone (a menu) | `material-boot` alone |
| `material-grub colour`, `conf`, `presets`, `overrides` | `material-boot core colour`, `conf`, `presets`, `overrides` ([customising.md](customising.md)) |
| `material-grub gui` | `material-boot ui` ([the editor](https://github.com/LucaCraft89/material-boot-core/blob/main/docs/editor.md)) |
| `material-grub update [--check]`, `version` | `sudo material-boot core install` (updates what is installed), `material-boot version` |
| `material-grub plymouth ...` | `material-boot plymouth ...` |

Typing an old word (`material-boot grub colour`) prints where it went. The installer removes the old `material-grub` command from `/usr/local/bin` (backed up first); the hooks that run after a kernel change (the Debian kernel hook, the Arch pacman hook) call `material-boot grub apply`.
