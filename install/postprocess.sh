#!/bin/sh
for f in /boot/grub2/grub.cfg /boot/grub/grub.cfg; do
  [ -f "$f" ] && python3 /usr/share/material-grub/bin/material-grub-classes "$f"
done
exit 0
