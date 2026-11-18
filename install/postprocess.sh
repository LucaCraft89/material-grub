#!/bin/sh
# Re-apply Material GRUB: annotate grub.cfg, refresh the BLS mirrors, bake the per-entry scenes.
# Normal systems run this after grub-mkconfig / entry changes. Immutable (ostree) installs add /var/lib/material-grub/env.
PKG=/usr/share/material-grub; PY=python3; MG_IMMUTABLE=0; MG_RES=1920x1080; MG_TIMEOUT=5
[ -f /var/lib/material-grub/env ] && . /var/lib/material-grub/env      # sets MATERIAL_PKG, MATERIAL_PY, MG_IMMUTABLE, MG_RES, MG_TIMEOUT
[ -n "$MATERIAL_PKG" ] && PKG=$MATERIAL_PKG; [ -n "$MATERIAL_PY" ] && PY=$MATERIAL_PY
# one run at a time: the installer, grub-mkconfig and the systemd path unit can all start this at once
if [ -z "$MG_LOCKED" ] && command -v flock >/dev/null; then MG_LOCKED=1 exec flock /run/material-grub.lock "$0" "$@"; fi

# The work (annotate, bake scenes) and the safety net (validate, roll back, notify) are in Python: bin/material-grub-postprocess
if [ "$MG_IMMUTABLE" = 1 ]; then
  # /boot may be mounted read-only on some immutable systems: open it for this run only
  RO=0; if grep -qE ' /boot [^ ]+ ro[ ,]' /proc/mounts; then RO=1; mount -o remount,rw /boot || exit 1; fi
  "$PY" "$PKG/bin/material-grub-postprocess" --pkg "$PKG" --immutable --res "$MG_RES" --timeout "$MG_TIMEOUT" "$@"; rc=$?
  [ "$RO" = 1 ] && mount -o remount,ro /boot
  exit $rc
fi
exec "$PY" "$PKG/bin/material-grub-postprocess" --pkg "$PKG" "$@"
