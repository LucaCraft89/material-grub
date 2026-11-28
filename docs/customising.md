# Customising

Two layers, both applied without a rebuild (only the dark/light scheme and the resolution are build choices):

- **Runtime options** in `/etc/material-grub.conf`: `STYLE`, `COOKIE`, `LOGO`, `HINTS`, `RAW_NAME`, `COUNTDOWN`, `TIMEOUT`, and, for the optional Plymouth part ([plugins.md](plugins.md)), `PLYMOUTH`, `PLYMOUTH_BAR`, `PLYMOUTH_MOTION` (they do nothing without it). Apply with `sudo material-boot grub apply` (the path unit also re-applies when the file changes). `sudo ./install.sh --no-hints` writes `HINTS=off` for you.
- **Overrides** in `/etc/material-grub/overrides.json`: one colour for the whole theme, a colour, name and icon per entry, hiding entries, and the order of the menu. The [editor](gui.md) edits this file with a live preview; you can also write it by hand. `sudo material-boot grub apply` applies it, and `material-boot grub doctor` checks it.

## overrides.json

```json
{
  "version": 1,
  "seed":    {"mode": "single", "color": "#7E57C2"},
  "groups":  ["windows", "linux", "system"],
  "order":   [{"key": "windows11"}, {"class": "mg_1a2b3c4d5e"}],
  "entries": [
    {"match": {"key": "fedora"}, "name": "Work laptop", "color": "#2E7D32", "icon": "tux"},
    {"match": {"title": "windows"}, "icon": "file:my-logo.png"},
    {"match": {"title": "memtest"}, "hidden": true}
  ]
}
```

- **seed** `mode`: `multi` (the default: every distro keeps its brand colour) or `single` (every entry uses the Material 3 palette of one seed colour). `sudo ./install.sh --seed '#7E57C2'` (or the colour step of the installer's TUI, with 32 preset colours) writes it.
- **entries** are rules, first match wins. A `match` is exactly one of `{"key": "fedora"}` (every entry of that catalog distro, it keeps working after kernel updates), `{"class": "mg_..."}` (one entry; the class changes when its title does) or `{"title": "text"}` (the entry's title contains the text, any case). A rule may set `name`, `color` (`#RRGGBB`), `icon` and `hidden`.
- **icon** is a catalog key (`tux`, `arch`, ...) or `file:NAME` for a picture in `/etc/material-grub/icons/` (PNG, JPEG, SVG, WEBP, GIF or BMP). A picture is drawn in full colour on a white badge on the entry's screen and as a one-colour shape in the rail and list rows. SVG needs `rsvg-convert` (the installer already requires it).
- **groups** orders the sections (`linux`, `windows`, `system`); **order** orders entries inside them (or everywhere when `groups` is empty). The real GRUB menu is reordered, not only the pictures.
- **hidden** removes the entry from the GRUB menu (nothing is deleted from disk).

What cannot be done, and why: entries that GRUB creates inside an `if` block or a function (usually `UEFI Firmware Settings`) are left alone, because moving or removing a block from inside a construct could break the script. If `grub.cfg` chooses its default entry by number (`set default="0"`), hiding and reordering are skipped, because they would change which entry is the default. A bad overrides file never breaks the boot: it is reported by `doctor` and ignored.

Pictures of each of these in real GRUB: [showcase.md](showcase.md).

## Presets

A preset is the whole look (style, options, overrides, the pictures) saved under a name, in the editor's *Presets* page, as a JSON file you can move to another machine. Dark/light and the resolution are not part of it.

## Ventoy sticks

The same format lives on the stick: `ventoy/material-grub-overrides.json`, with `{"match": {"title": "text of the file name"}}` rules, pictures in `ventoy/material-grub-icons/`. A customised file gets its own scene, a `menu_class` rule (the shortest piece of its name no other file has) and, with a `name`, that name drawn on its screen (plus a Ventoy `menu_alias`, which Ventoy 1.1.18 does not show in its list). Hiding and ordering do not apply to Ventoy (it sorts by name). See [ventoy.md](ventoy.md).

## For contributors

- **Seed colours, names, aliases:** `scripts/catalog.py` is the single source of truth. Colours marked `proposed` are hand-picked, not official; open a PR to change them. Rebuild with `make package`.
- **Add a distro:** a row in `catalog.py`; the full guide is [adding-a-distro.md](adding-a-distro.md). Unknown distros fall back to Tux.
- **Layout and shapes:** `scripts/render_scene.py` (the background panels) and `install/bin/mgscenes.py` (hero, pills, rail, drawn at config time; it also redraws the panels for custom colours, `Renderer.panel_scene`).
