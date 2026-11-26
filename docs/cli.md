# The `material-grub` command

One command for everything. Run it alone for a menu (a terminal UI; arrows and Enter, `q` quits), or give it a subcommand:

| Command | What it does |
|---|---|
| `material-grub` | a menu of everything below |
| `material-grub doctor [--json]` | check the installation (`status` is an alias); paste it into a bug report |
| `sudo material-grub apply` | regenerate `grub.cfg` and re-apply the theme (also reads `overrides.json`) |
| `material-grub gui` | the optional graphical editor ([gui.md](gui.md)) |
| `material-grub preview` | your own boot entries rendered as a web page, nothing is installed |
| `material-grub colour [#RRGGBB \| name \| multi]` | one seed colour for the whole theme (32 names such as `forest`, `tangerine`), or back to a colour per entry; `--apply` applies it at once |
| `material-grub presets list \| save NAME \| apply NAME \| delete NAME \| export NAME FILE \| import FILE` | looks you saved |
| `material-grub overrides show \| check \| path \| edit` | the overrides file ([customising.md](customising.md)); `edit` opens your `$EDITOR` and validates before saving |
| `material-grub conf [KEY=VALUE]` | show or change the runtime options (`STYLE=list`, `HINTS=off`, ...) |
| `material-grub ventoy [STICK] [options]` | theme a Ventoy stick; without `STICK` the mounted one is found ([ventoy.md](ventoy.md)) |
| `material-grub update [--check]` | the installed version, a look at GitHub when you ask, and how to update |
| `sudo material-grub uninstall` | remove Material GRUB (your settings in `/etc` stay) |
| `material-grub <part> ...` | an optional part from another package when it is installed, for example `material-grub plymouth ...` ([plugins.md](plugins.md)); without it the command says so |
| `material-grub version`, `help` | `version` also lists the installed parts |

Commands that write system files ask for root themselves: in a terminal they re-run through `sudo` (your password or fingerprint), otherwise they tell you to run `sudo material-grub ...`. It is the only command that is installed: `apply`, `gui` and the rest are subcommands (since 0.7.1; earlier versions also installed `material-grub-apply` and `material-grub-gui`, which an update removes).
