# Adding or fixing a distro

Every distro is one row in `scripts/catalog.py` (the list `D`). Everything else (scenes, palettes, class
matching, `titles.json`, `rules.json`, rail glyphs) is generated from it by `scripts/package.py`.

## 1. The row

```python
(("cachyos", "CachyOS", "Arch-based, optimized", FL % "cachyos", "#2BB5A0", "proposed", ["cachy", "cachy_os"]),)
#  key        title       subtitle                glyph            seed      source      aliases
```

| Field | Meaning |
|---|---|
| `key` | Unique lowercase id. Also an alias for itself. Used for the per-entry scene file names, so keep it `[a-z0-9]+`. |
| `title` | The big name on the scene. Long names shrink to fit, but 14 characters or fewer looks best. |
| `subtitle` | Small line under the name, shown for entries that have no info pills (plain entries). |
| `glyph` | Path to an SVG, drawn as a single-colour mask (so any fill colour in the SVG is ignored). `FL % "name"` = `vendor/font-logos/src/vectors/name.svg`, `MS % "name"` = `vendor/material-symbols/name.svg`. `None` falls back to the Tux glyph. |
| `seed` | Hex colour fed into the Material 3 *Expressive* scheme; the whole screen is derived from it (light and dark). Use the brand's primary colour. Very dark or very grey seeds give dull scenes; nudge them toward a mid-tone, saturated variant. |
| `source` | `chosen` (maintainer decision), `si` (taken from Simple Icons, CC0) or `proposed` (hand-picked, open to change). Use `si` only if the hex really is the Simple Icons value. |
| `aliases` | Extra lowercase names to match (see below). |

Order matters: rows are shown in the section rail in the order they appear, Linux distros first, then
Windows, then System. Put new Linux distros inside the Linux block, before `tux`.

## 2. Glyph sources

1. Look in `vendor/font-logos/src/vectors/` (a few hundred logos).
2. Otherwise drop a **simple, single-path, monochrome** SVG into `vendor/` (for example `vendor/extra/yourdistro.svg`) and point `glyph` at it. Check the licence and add a line to `THIRD_PARTY.md`. Distro logos are trademarks of their owners; only use them to identify the boot entry.
3. Rendering uses `rsvg-convert`; if it draws your SVG correctly, the build will too.

## 3. How entries are matched to a row

At config time, `install/bin/material-grub-classes` looks at every GRUB entry title and picks a row:

1. **Title tokens, case-insensitive.** `rules.json` is generated from `title`, `key` and every alias, split into lowercase alphanumeric tokens (`Pop!_OS` -> `pop`, `os`). An entry matches when those tokens appear next to each other, in order, in the entry title. The longest rule wins, so `Linux Mint` beats `Linux`.
2. **GRUB's `--class`.** If no title matches, the entry's `--class` values (or a BLS `grub_class`) are compared with the aliases.
3. **Windows** is detected by name (`windows`, `microsoft`); the build number in `bootmgfw.efi` decides Windows 10 or 11.
4. Anything else becomes **Tux**.

Aliases are therefore for the spellings GRUB actually emits: the `ID=` from `/etc/os-release` (`opensuse-tumbleweed`), the `--class` GRUB generates (`kali`, `ubuntu`) and common title variants. Words that are too generic are ignored (`os`, `gnu`, `linux`, ...; see `GENERIC` in `scripts/package.py`), so don't add them.

## 4. Test it

```sh
python3 -m venv .venv && .venv/bin/pip install --require-hashes -r requirements.txt   # once
make package                              # rebuild scenes, about 3 minutes (or: .venv/bin/python scripts/package.py --res 1920x1080)
make screenshots                          # boots the theme in QEMU + OVMF, writes docs/screenshots/
```

`make screenshots` rewrites the gallery images; the images it updates unintentionally should not be committed
(`git checkout docs/screenshots`). To look at *your* distro, add a `menuentry` for it to `CFG` in
`scripts/make_screenshots.py` or run the VM by hand:

```sh
.venv/bin/python scripts/qemu_tree.py build/shots-tree 1920x1080 down down ret   # keys: down up ret esc
# screenshots are written to build/tree-N.png
```

Also check the light scheme (`--scheme light`), since seeds that look fine dark can wash out light.

Check name matching without a VM:

```sh
.venv/bin/python - <<'PY'
import sys; sys.path.insert(0, "install/bin"); import mgrub, json
rules = json.load(open("dist/material-grub/rules.json"))
for t in ["CachyOS Linux", "Your Distro GNU/Linux (6.8.0) 24.04", "Some Unknown OS"]:
    print(t, "->", mgrub.key_for(t, rules))
PY
```

## 5. Open the PR

Fill in the PR template: the row, a screenshot of the scene (dark is enough, light is a bonus), the title GRUB shows for
your distro (`grep -E "menuentry|^title" /boot/grub*/grub.cfg /boot/loader/entries/*.conf`) and whether the seed colour is the
official brand colour (`si`/`chosen`) or your guess (`proposed`).
