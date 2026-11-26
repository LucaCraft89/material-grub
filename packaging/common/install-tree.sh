#!/bin/sh
# Copies the source tree a package ships into DESTDIR/usr/share/material-grub-src (used by the PKGBUILD, the spec and debian/rules).
# The theme is NOT part of the package: it is built from these sources on the target machine by `install.sh --from-package`.
# usage: install-tree.sh SRCDIR DESTDIR
set -e
src=$1; dest=$2/usr/share/material-grub-src
install -d "$dest"
for f in install.sh requirements.txt VERSION LICENSE THIRD_PARTY.md README.md material-boot-part.json; do install -m644 "$src/$f" "$dest/$f"; done
chmod 755 "$dest/install.sh"
for d in install scripts vendor fonts; do cp -a "$src/$d" "$dest/$d"; done
find "$dest" -name __pycache__ -type d -prune -exec rm -rf {} +
install -d "$2/etc"
install -m644 "$src/install/material-grub.conf" "$2/etc/material-grub.conf"
# the part's manifest for material-boot (plugin API 2): the package owns it, and its entry is the copy of the sources that has the installer
install -d "$2/usr/share/material-boot/plugins.d"
sed 's|"entry": "install/part_grub.py"|"entry": "/usr/share/material-grub-src/install/part_grub.py"|' "$src/material-boot-part.json" > "$2/usr/share/material-boot/plugins.d/grub.json"
chmod 644 "$2/usr/share/material-boot/plugins.d/grub.json"
