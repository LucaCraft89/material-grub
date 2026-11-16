#!/bin/sh
set -e
systemctl disable --now material-grub.path 2>/dev/null || true
rm -rf /usr/share/material-grub /etc/grub.d/05_material /usr/libexec/material-grub-postprocess /etc/systemd/system/material-grub.* /boot/grub2/themes/material /boot/grub/themes/material
if command -v grub2-mkconfig >/dev/null; then grub2-mkconfig -o /boot/grub2/grub.cfg; else grub-mkconfig -o /boot/grub/grub.cfg; fi
echo "material-grub removed (GRUB_GFXMODE in /etc/default/grub left as is)"
