#!/bin/sh
PKG=/usr/share/material-grub
for f in /boot/grub2/grub.cfg /boot/grub/grub.cfg; do
  [ -f "$f" ] && python3 "$PKG/bin/material-grub-classes" "$f"
done
for t in /boot/grub2/themes/material /boot/grub/themes/material; do
  [ -d "$t" ] && python3 "$PKG/bin/material-grub-rail" --theme "$t"
done
exit 0
