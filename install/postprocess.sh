#!/bin/sh
PKG=/usr/share/material-grub
# one run at a time: the installer, grub-mkconfig and the systemd path unit can all start this at once
if [ -z "$MG_LOCKED" ] && command -v flock >/dev/null; then MG_LOCKED=1 exec flock /run/material-grub.lock "$0" "$@"; fi
for f in /boot/grub2/grub.cfg /boot/grub/grub.cfg; do
  [ -f "$f" ] && python3 "$PKG/bin/material-grub-classes" "$f"
done
for t in /boot/grub2/themes/material /boot/grub/themes/material; do
  [ -d "$t" ] && python3 "$PKG/bin/material-grub-scenes" --theme "$t"
done
exit 0
