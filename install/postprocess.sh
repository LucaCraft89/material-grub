#!/bin/sh
# Re-apply Material GRUB: annotate grub.cfg, refresh the BLS mirrors, bake the per-entry scenes.
# Normal systems run this after grub-mkconfig / entry changes. Immutable (ostree) installs add /var/lib/material-grub/env.
PKG=/usr/share/material-grub; PY=python3; MG_IMMUTABLE=0; MG_RES=1920x1080; MG_TIMEOUT=5
[ -f /var/lib/material-grub/env ] && . /var/lib/material-grub/env      # sets MATERIAL_PKG, MATERIAL_PY, MG_IMMUTABLE, MG_RES, MG_TIMEOUT
[ -n "$MATERIAL_PKG" ] && PKG=$MATERIAL_PKG; [ -n "$MATERIAL_PY" ] && PY=$MATERIAL_PY
# one run at a time: the installer, grub-mkconfig and the systemd path unit can all start this at once
if [ -z "$MG_LOCKED" ] && command -v flock >/dev/null; then MG_LOCKED=1 exec flock /run/material-grub.lock "$0" "$@"; fi

if [ "$MG_IMMUTABLE" = 1 ]; then
  # /boot may be mounted read-only on some immutable systems: open it for this run only
  RO=0; if grep -qE ' /boot [^ ]+ ro[ ,]' /proc/mounts; then RO=1; mount -o remount,rw /boot || exit 1; fi
  for f in /boot/grub2/grub.cfg /boot/grub/grub.cfg; do
    [ -f "$f" ] || continue
    real=$(readlink -f "$f"); gdir=$(dirname "$real")
    if mountpoint -q /boot 2>/dev/null; then mbase=${gdir#/boot}/material; else mbase=$gdir/material; fi
    # mirrors live next to grub.cfg, NOT in /boot/loader: ostree swaps that directory on every deployment
    "$PY" "$PKG/bin/material-grub-static" "$f" --mode "$MG_RES" --pkg "$PKG" --timeout "$MG_TIMEOUT" &&
    "$PY" "$PKG/bin/material-grub-classes" "$f" --pkg "$PKG" --mirrors "$gdir/material" --mirrorbase "$mbase" --fallback-all
    [ -d "$gdir/themes/material" ] && "$PY" "$PKG/bin/material-grub-scenes" --theme "$gdir/themes/material" --pkg "$PKG"
  done
  [ "$RO" = 1 ] && mount -o remount,ro /boot
  exit 0
fi

for f in /boot/grub2/grub.cfg /boot/grub/grub.cfg; do
  [ -f "$f" ] && "$PY" "$PKG/bin/material-grub-classes" "$f" --pkg "$PKG"
done
for t in /boot/grub2/themes/material /boot/grub/themes/material; do
  [ -d "$t" ] && "$PY" "$PKG/bin/material-grub-scenes" --theme "$t" --pkg "$PKG"
done
exit 0
