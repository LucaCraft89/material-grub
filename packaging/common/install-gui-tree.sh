#!/bin/sh
# Installs the optional GUI into DESTDIR (used by the spec, debian/rules, the PKGBUILD and `install.sh --with-gui`). Unlike the main package nothing is built:
# the GUI is plain Python and web files that run on the theme package (material-grub) already installed.
# usage: install-gui-tree.sh SRCDIR DESTDIR
set -e
src=$1; dest=$2
share=$dest/usr/share/material-grub-gui
install -d "$share/web" "$dest/usr/bin" "$dest/usr/libexec" "$dest/usr/share/polkit-1/actions" "$dest/usr/share/applications"
for f in mgpaths.py mgstate.py mgpreview.py mgserver.py; do install -m644 "$src/gui/$f" "$share/$f"; done
install -m644 "$src/install/ventoy_sticks.py" "$share/ventoy_sticks.py"
install -m755 "$src/gui/material-grub-gui" "$share/material-grub-gui"
for f in "$src"/gui/web/*; do install -m644 "$f" "$share/web/$(basename "$f")"; done
ln -sf ../share/material-grub-gui/material-grub-gui "$dest/usr/bin/material-grub-gui"
install -m755 "$src/gui/mghelper.py" "$dest/usr/libexec/material-grub-gui-helper"
install -m644 "$src/gui/org.material-grub.gui.policy" "$dest/usr/share/polkit-1/actions/org.material-grub.gui.policy"
install -m644 "$src/gui/material-grub-gui.desktop" "$dest/usr/share/applications/material-grub-gui.desktop"
