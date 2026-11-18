# Using Material GRUB, start to finish

A tour in the order you will meet things. Reference pages: [install](install.md), [the `material-grub` command](cli.md), [customising and `overrides.json`](customising.md), [the GUI](gui.md), [Ventoy](ventoy.md), [how it works](how-it-works.md).

## 1. Install (once)

```sh
git clone https://github.com/LucaCraft89/material-grub.git
cd material-grub
sudo ./install.sh
```

In a terminal this opens the installer's questions. Left: the current question; right: what the highlighted option means; the last tab is a summary with the equivalent command. Keys: Up/Down choose, Enter next, Left back, `q` quits without changing anything.

| Question | Meaning |
|---|---|
| Resolution | your screen (the primary monitor is proposed); GRUB draws at this size |
| Style | `rail`, `clean`, `list` or `split` (see the [gallery](gallery.md)) |
| Colour scheme | dark or light (chosen when the images are built) |
| Colours | *every entry its own colour* (the default) or *one colour for the whole theme*, then one of 32 seed colours or any `#RRGGBB` |
| Cookie and firmware logo, key hints, extras | the top-right cookie (with your machine's own boot logo inside, or the Linux penguin when the firmware has none), the key-hint pills, the raw-name line, the countdown bar, the timeout |
| Graphical editor | **yes or no** (default no): the optional GUI, see below |

It then builds the theme from source (a few minutes), backs up your GRUB files to `/var/backups/material-grub`, installs, and regenerates `grub.cfg`. Reboot to see it. Packages (`dnf`, `apt`, `pacman`) use the same pipeline without questions; scripts can pass flags (`--yes --no-tui --style list --seed '#7E57C2' ...`).

Not sure about it? `./install.sh --preview` shows your own menu as a web page first (no root, nothing installed), and `sudo ./install.sh --dry-run` shows what would change.

## 2. Everything afterwards: `material-grub`

Run `material-grub` alone: a menu of everything (arrows and Enter, `q` quits). The same things as subcommands:

```sh
material-grub doctor                # is everything installed and valid? (paste it into a bug report)
sudo material-grub apply            # re-apply after changing settings or overrides
material-grub gui                   # the graphical editor
material-grub colour forest         # one seed colour for everything (or #RRGGBB; `multi` goes back)
material-grub conf STYLE=list       # runtime options: STYLE, COOKIE, LOGO, HINTS, RAW_NAME, COUNTDOWN, TIMEOUT
material-grub presets save "My look"
material-grub overrides edit        # colours, names, icons, order, hidden entries, in your $EDITOR
material-grub ventoy                # (re)write the theme on a mounted Ventoy stick
material-grub update --check        # is there a new release?
```

Anything that writes a system file asks for root itself (through `sudo`: your password or fingerprint). Every subcommand is in [cli.md](cli.md).

## 3. Make it yours

What you can change without rebuilding: the style and the options (`material-grub conf`), one colour for the whole theme, and per entry a colour, a name, an icon (the built-in ones or your own PNG, JPEG or SVG), hiding it, and the order of the menu (windows first or linux first, or any order you like). All of it lives in `/etc/material-grub/overrides.json` and is applied by `sudo material-grub apply` (the settings file is also watched, so editing it re-applies by itself; hiding and reordering need `apply`). Format and limits: [customising.md](customising.md).

Only two things are chosen when the images are built: dark or light, and the resolution. To change them, run the installer again (`sudo ./install.sh --scheme light`).

## 4. The GUI (optional)

Say yes to the installer's question, or later `sudo ./install.sh --with-gui` (or the `material-grub-gui` package). Start it with `material-grub gui`: it opens in your browser.

- **Overview**: health checks and shortcuts.
- **Style**: pick the layout and options and watch the preview.
- **Entries**: drag entries to reorder, *Linux first* / *Windows first*, and for the selected entry its name, colour, icon and visibility. *Applies to* decides whether a change covers every entry of that distro (it keeps working after kernel updates) or only one entry.
- **Colours**: one seed colour for all, or a colour per entry.
- **Ventoy**: pick a mounted stick, set its look, customise single ISOs.
- **Presets**: save the look, export it to a file, import it on another machine.
- **Update**: look for a new release (only when you click) and update.

The **live preview** on the right is drawn by the same code that writes your real menu, including your firmware logo in the cookie. Nothing is written until you press **Apply to GRUB**: a password or fingerprint prompt appears (the GUI itself never runs as root), a pop-up shows the progress with a verbose log, and if applying fails your previous settings come back. Details and safety: [gui.md](gui.md).

## 5. A Ventoy stick

```sh
./install.sh --ventoy         # the first time: a TUI picks the stick, the style, the scheme and the resolutions
material-grub ventoy          # afterwards: finds the mounted stick and re-writes the theme with the stick's own settings
```

No root is needed. Add, rename and remove ISOs on any computer afterwards: nothing has to run again (dynamic mode). To rename, recolour or re-icon single images, use the GUI's Ventoy page or `ventoy/material-grub-overrides.json` on the stick. See [ventoy.md](ventoy.md).

## 6. Updating

- **Packages:** your normal updates (`dnf upgrade`, `apt upgrade`, `pacman -Syu`) rebuild and re-apply the theme with the same safety nets.
- **From a clone:** `git pull && sudo ./install.sh` (your settings and overrides are kept).
- `material-grub update --check` or the GUI's Update page tell you whether a new release exists.

## 7. When something looks wrong

1. `material-grub doctor`: it says what is wrong and which command fixes it (usually `sudo material-grub apply`).
2. If GRUB ever shows its plain menu instead of the theme, that is the safety net: the theme was incomplete or `grub.cfg` failed validation and was rolled back. `doctor` shows the reason; `/var/log/material-grub/install.log` has the installer's log.
3. Overrides do something unexpected? `material-grub overrides check`. A broken file is ignored, never fatal.
4. Anything else: the issue templates ask for the `doctor` output.

## 8. Going back

`sudo ./install.sh --uninstall` (or `sudo material-grub uninstall`) restores your GRUB and removes the theme, the hooks and the GUI. Your settings in `/etc/material-grub.conf` and `/etc/material-grub/` stay, so reinstalling brings your look back. The backups of your original files stay in `/var/backups/material-grub`.
