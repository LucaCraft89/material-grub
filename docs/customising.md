# Customising

- **Runtime options:** `/etc/material-grub.conf` (`RAW_NAME`, `COUNTDOWN`, `LOGO`, `COOKIE`, `HINTS`, `TIMEOUT`, `STYLE`); apply with `sudo material-grub-apply`. The top-right cookie and the key-hint pills are drawn at install/apply time, not baked into the downloaded images, so they are switchable without a rebuild (`sudo ./install.sh --no-hints` writes `HINTS=off`). Only the colour scheme is still a build choice.

- **Seed colours, names, aliases:** `scripts/catalog.py` is the single source of truth. Colours marked `proposed` are hand-picked, not official, and are happy to be changed (open a PR). Rebuild with `make package`.
- **Add a distro:** add a row to `catalog.py` (key, title, subtitle, glyph, seed colour, aliases); the full guide is [docs/adding-a-distro.md](docs/adding-a-distro.md). Unknown distros already fall back to Tux.
- **Layout and shapes:** `scripts/render_scene.py` (background scene) and `install/bin/material-grub-scenes` (hero, pills, rail, drawn at config time).


