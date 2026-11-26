#!/bin/sh
# Lays out the files a package of the core ships (used by the spec, the PKGBUILD and debian/rules).
# The shared DATA is not part of the package: it depends on the scheme, so it is built on the target machine by
# `material-boot core install --from-package --only core` (the package's post-install step).
# usage: install-tree.sh SRCDIR DESTDIR
set -e
src=$1; dest=$2; p=$dest/usr/share/material-boot
install -d "$p/lib" "$p/scripts" "$p/plugins.d" "$dest/usr/bin"
cp -a "$src/material_boot" "$p/lib/material_boot"
find "$p" -name __pycache__ -type d -prune -exec rm -rf {} +
install -m644 "$src/VERSION" "$p/lib/material_boot/VERSION"
install -m755 "$src/scripts/build_data.py" "$p/scripts/build_data.py"
cp -a "$src/assets" "$p/assets"
install -m755 "$src/bin/material-boot" "$dest/usr/bin/material-boot"
