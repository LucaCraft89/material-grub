#!/bin/sh
set -e
systemctl disable --now material-grub.path material-grub-finalize.service 2>/dev/null || true
[ -f /var/lib/material-grub/env ] && . /var/lib/material-grub/env
if [ -f /var/lib/material-grub/env ] && grep -q '^MG_IMMUTABLE=1' /var/lib/material-grub/env; then
  # immutable install: put the static grub.cfg back as it was before we first touched it, then remove everything we added
  RO=0; if grep -qE ' /boot [^ ]+ ro[ ,]' /proc/mounts; then RO=1; mount -o remount,rw /boot; fi
  for f in /boot/grub2/grub.cfg /boot/grub/grub.cfg; do
    [ -f "$f" ] || continue
    "${MATERIAL_PY:-python3}" /var/lib/material-grub/pkg/bin/material-grub-static "$f" --restore || echo "WARNING: no pristine copy of $f; restore it from /var/backups/material-grub or run 'bootupctl update'"
    rm -rf "$(dirname "$(readlink -f "$f")")/themes/material" "$(dirname "$(readlink -f "$f")")/material"
  done
  [ "$RO" = 1 ] && mount -o remount,ro /boot
  rm -f /usr/bin/material-grub-gui /usr/libexec/material-grub-gui-helper /usr/share/polkit-1/actions/org.material-grub.gui.policy /usr/share/applications/material-grub-gui.desktop; rm -rf /usr/share/material-grub-gui   # the optional GUI (source installs; a package removes its own files)
  rm -f /usr/local/bin/material-grub /usr/local/sbin/material-grub /usr/local/bin/material-grub-apply /usr/local/sbin/material-grub-apply
  rm -rf /var/lib/material-grub /etc/systemd/system/material-grub.* /etc/systemd/system/material-grub-finalize.service
  systemctl daemon-reload 2>/dev/null || true
  echo "(your /etc/material-grub.conf and /etc/material-grub/ with your overrides, icons and presets were kept)"; echo "material-grub removed (immutable install); backups stay in /var/backups/material-grub"
  exit 0
fi
rm -f /usr/bin/material-grub-gui /usr/libexec/material-grub-gui-helper /usr/share/polkit-1/actions/org.material-grub.gui.policy /usr/share/applications/material-grub-gui.desktop; rm -rf /usr/share/material-grub-gui   # the optional GUI (source installs; a package removes its own files)
rm -f /usr/local/bin/material-grub /usr/local/sbin/material-grub /usr/local/bin/material-grub-apply /usr/local/sbin/material-grub-apply
rm -f /usr/share/material-boot/plugins.d/grub.json     # the part's manifest for `material-boot`
[ "${MATERIAL_BOOT_UNIFIED:-}" = 1 ] || rm -f /var/lib/material-grub/state.json     # the record of what is installed (the unified installer keeps it: it holds the other parts too)
rm -rf /usr/share/material-grub /etc/grub.d/05_material /etc/grub.d/15_material_menu /etc/grub.d/90_material_system /usr/libexec/material-grub-postprocess /etc/systemd/system/material-grub.* /boot/grub2/themes/material /boot/grub/themes/material
if command -v grub2-mkconfig >/dev/null; then grub2-mkconfig -o /boot/grub2/grub.cfg; else grub-mkconfig -o /boot/grub/grub.cfg; fi
echo "(your /etc/material-grub.conf and /etc/material-grub/ with your overrides, icons and presets were kept; the GUI was removed too)"
echo "material-grub removed (GRUB_GFXMODE in /etc/default/grub left as is)"
