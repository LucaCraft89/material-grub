# The graphical editor

The editor is not part of Material GRUB any more: since 1.2.0 it is **`material-boot ui`**, in [material-boot-core](https://github.com/LucaCraft89/material-boot-core/blob/main/docs/editor.md), one editor for the menu, the boot splash and Ventoy, with a live preview. This page stays so that old links work.

- Start it: *Material Boot* in your applications menu, or `material-boot ui`.
- Its **Style**, **Entries** and **Ventoy** pages are this theme's; what each does is described in [the editor's page](https://github.com/LucaCraft89/material-boot-core/blob/main/docs/editor.md).
- The installer puts its launcher in place by default on a machine with a graphical session (`--without ui` skips it). The old `material-grub-gui` package and `--with-gui` are gone.

![The editor](screenshots/gui/entries.png)
