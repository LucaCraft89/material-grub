#!/bin/sh
# usage: sudo ./install.sh [--res WxH] [--dest DIR] [--no-run]   (DESTDIR-style staging with --dest)
set -e
HERE=$(cd "$(dirname "$0")" && pwd); PKG=$HERE/../dist/material-grub
D=""; RES=""; RUN=1
while [ $# -gt 0 ]; do case $1 in --dest) D=$2; shift;; --res) RES=$2; shift;; --no-run) RUN=0;; esac; shift; done
[ -d "$PKG" ] || { echo "run scripts/package.py first"; exit 1; }
install -d "$D/usr/share/material-grub" "$D/usr/libexec" "$D/etc/grub.d" "$D/etc/systemd/system"
cp -a "$PKG/." "$D/usr/share/material-grub/"
chmod +x "$D/usr/share/material-grub/bin/"*
install -m755 "$HERE/postprocess.sh" "$D/usr/libexec/material-grub-postprocess"
install -m755 "$HERE/05_material" "$D/etc/grub.d/05_material"
install -m644 "$HERE"/systemd/material-grub.* "$D/etc/systemd/system/"
if [ -z "$D" ]; then
  B=/var/backups/material-grub; mkdir -p "$B"
  [ -f "$B/default-grub.orig" ] || cp -a /etc/default/grub "$B/default-grub.orig"
  for f in /boot/grub2/grub.cfg /boot/grub/grub.cfg; do [ -f "$f" ] && [ ! -f "$B/$(echo $f | tr / _).orig" ] && cp -a "$f" "$B/$(echo $f | tr / _).orig"; done
  echo "backups in $B"
fi
if [ -n "$RES" ] && [ -z "$D" ]; then
  if grep -q '^GRUB_GFXMODE=' /etc/default/grub; then sed -i "s/^GRUB_GFXMODE=.*/GRUB_GFXMODE=$RES/" /etc/default/grub; else echo "GRUB_GFXMODE=$RES" >> /etc/default/grub; fi
fi
if [ -z "$D" ] && [ $RUN = 1 ]; then
  systemctl daemon-reload; systemctl enable --now material-grub.path
  if command -v grub2-mkconfig >/dev/null; then grub2-mkconfig -o /boot/grub2/grub.cfg; else grub-mkconfig -o /boot/grub/grub.cfg; fi
  /usr/libexec/material-grub-postprocess
fi
echo "installed${D:+ to $D}"
