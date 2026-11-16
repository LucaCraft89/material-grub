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
if [ -n "$RES" ] && [ -z "$D" ]; then
  if grep -q '^GRUB_GFXMODE=' /etc/default/grub; then sed -i "s/^GRUB_GFXMODE=.*/GRUB_GFXMODE=$RES/" /etc/default/grub; else echo "GRUB_GFXMODE=$RES" >> /etc/default/grub; fi
fi
if [ -z "$D" ] && [ $RUN = 1 ]; then
  systemctl daemon-reload; systemctl enable --now material-grub.path
  if command -v grub2-mkconfig >/dev/null; then grub2-mkconfig -o /boot/grub2/grub.cfg; else grub-mkconfig -o /boot/grub/grub.cfg; fi
  /usr/libexec/material-grub-postprocess
fi
echo "installed${D:+ to $D}"
