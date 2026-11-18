# Install

One command. The installer detects your distro, **installs every dependency**, builds the theme in a temporary
directory, picks your screen resolution and installs it. It needs root, so run it with `sudo`:

```sh
git clone https://github.com/LucaCraft89/material-grub.git
cd material-grub
sudo ./install.sh
```

In a terminal this opens the installer's questions (see below); answer them and the rest runs by itself. Then reboot. That's it.
For everything after the install, see [usage.md](usage.md).

> ⚠️ This modifies your bootloader configuration. The installer backs up `/etc/default/grub` and `grub.cfg` to
> `/var/backups/material-grub`, and `sudo ./install.sh --uninstall` reverts everything. Know how to boot a live USB
> before you try it on your only machine.

**What it does** (it prints numbered steps and a live progress counter, so you can always see it is working; a full run takes about 2 to 4 minutes)

1. Installs dependencies with your package manager: GRUB tools (`mkconfig`, `mkfont`), librsvg (`rsvg-convert`), Python 3 with `venv` and `pip`,
   and Pillow. Supported: `dnf` (Fedora, RHEL family), `apt` (Debian, Ubuntu, Mint, Pop!_OS), `pacman` (Arch family),
   `zypper` (openSUSE), `apk` (Alpine), `xbps` (Void). Python build requirements (`fonttools`, `materialyoucolor`) go into a throw-away virtualenv.
2. Renders the scenes (a few minutes) into `/var/tmp`, leaving the cloned repository untouched.
3. Auto-detects the resolution (existing `GRUB_GFXMODE`, otherwise your panel's preferred mode) and sets `GRUB_GFXMODE`.
4. Installs the package to `/usr/share/material-grub`, the hooks to `/etc/grub.d/` (`05_material`, `15_material_menu`,
   `90_material_system`) and a systemd path unit that re-applies everything when `grub.cfg`, `/boot/loader/entries` or
   `grubenv` change, then regenerates `grub.cfg`.

**Options**

```sh
sudo ./install.sh --res 1920x1200   # force a resolution instead of auto-detecting
sudo ./install.sh --scheme light    # light variant instead of dark
sudo ./install.sh --style list      # rail (default) | clean | list | split; also --no-hints, --no-cookie, --no-logo
sudo ./install.sh --seed '#7E57C2'  # one seed colour for every entry (--seed-mode multi goes back to a colour per entry)
sudo ./install.sh --with-gui        # also install the optional GUI (the TUI asks this itself)
sudo ./install.sh --no-deps         # you installed the dependencies yourself
sudo ./install.sh --stage-only      # install deps and build, but do not touch GRUB
sudo ./install.sh --keep-build      # keep the temporary build directory
sudo ./install.sh --uninstall       # remove the theme and hooks
```

**Interactive installer (TUI).** Run in a terminal without `--yes`, `./install.sh` asks for whatever you did not give as a flag (resolution, style, colour scheme, **one colour for everything or a colour per entry** (with 32 preset colours), cookie/logo, key hints, extras, and **whether to install the optional GUI** (default: no); on immutable systems also your consent). Left: the current question and a tab strip of the steps; right: a call-out explaining the highlighted option; the last tab is a summary with the equivalent non-interactive command. The resolution step proposes your **primary monitor** (X11 `xrandr`, then GNOME/KDE/wlroots Wayland tools run as your own user, then the DRM sysfs, then `GRUB_GFXMODE`) and lets you pick another detected screen or type `WxH`. GRUB draws on whichever output the firmware chooses, usually the primary one. `--no-tui` (or `--yes`, or no terminal) keeps the fully automatic behaviour that scripts and CI need (the GUI is then only installed with `--with-gui`); `--tui` forces the questions. Without curses or with a dumb terminal it falls back to plain prompts. Status: the parsers are unit-tested on sample outputs and the TUI is driven through a pty at 80x24 in the tests; the GNOME (Mutter) parser has only been tested on a hand-written sample, and none of the desktop tools have been run on real multi-monitor setups here.

**Styles** (`STYLE` in `/etc/material-grub.conf`, change with `sudo material-grub apply`; the images are the same for all of them): `rail` is the full-screen design with an icon rail, `clean` is full screen with the previous and next entries peeking in above and below and label chips on the edges, `list` is a centred list of icon-in-shape plus name pill, `split` is the same list moved to the right with the selected entry's big logo and name on the left (separators between Linux, Windows and System included). `COOKIE`, `LOGO` and `HINTS` switch the top-right cookie, the firmware logo inside it and the key-hint pills.

The installer always builds the theme from source (there are no prebuilt downloads); `--pkg DIR` installs a package you built elsewhere, which is how immutable hosts without build tools work.

## Supported resolutions

`1280x720`, `1920x1080`, `1920x1200`, `2560x1080`, `2560x1440`, `2880x1800`, `3440x1440`, `3840x1080`, `3840x1600`, `3840x2160`, `5120x1440`, `5120x2160`.
Anything else snaps to the closest aspect ratio. The scene sets are 16:9, 16:10, 21:9 and 32:9; screens at least 1800 px high use a 2160-high set
(four times the pixels, about 20 MB per set). The installer builds only the set for the resolution it detects (or `--res`), so after
switching monitors or `GRUB_GFXMODE`, run `sudo ./install.sh --res WxH` again.

**Update:** `git pull && sudo ./install.sh`  **Uninstall:** `sudo ./install.sh --uninstall`. To restore the original
GRUB files, copy them back from `/var/backups/material-grub`.

**Not supported:** NixOS (declarative GRUB) and immutable/ostree systems such as Silverblue or Bazzite, where `/usr` is read-only
(`--force` tries anyway). Systems without systemd work, but you must re-run the installer after kernel changes.

<details>
<summary>Manual install for developers (make targets)</summary>

```sh
make venv        # virtualenv with the build requirements
make package     # render scenes + bundles into dist/material-grub
make install RES=1920x1200   # SCHEME=light for the light variant
```

The Google Sans Flex font is bundled in `fonts/` (SIL OFL 1.1, unmodified upstream copy). Set `GSF_FONT=/path/to/font.ttf` to use another copy.
</details>

## Other distros

The installer detects `grub2-mkconfig` (Fedora/RHEL) and `grub-mkconfig` (Debian, Ubuntu, Arch, ...). Classic
`menuentry`/`submenu` entries (Debian-family and Arch style "Advanced options for ...") are annotated and themed
directly. Fedora's BootLoaderSpec (BLS) entries get the *default kernel on top, rest under Advanced options*
structure through mirror directories in `/boot/loader/material-top` and `/boot/loader/material-adv`; Fedora's own
files are never edited. Systems without `blscfg` (Debian, Ubuntu, Arch: classic `menuentry`/`submenu`) are themed directly from `grub.cfg`; `blscfg` calls with `--path` or `--show-*` options are left untouched (themed by class, no pills or Advanced grouping). **Fedora 44 is the primary target; other distros have not been tested on real hardware.**



Immutable systems (Silverblue, Bazzite, ...): [immutable.md](immutable.md). Ventoy sticks: [ventoy.md](ventoy.md). Diagnosing problems: `sudo material-grub doctor`.
