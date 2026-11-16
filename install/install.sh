#!/bin/sh
# usage: sudo ./install.sh [--res WxH] [--dest DIR] [--no-run]   (DESTDIR-style staging with --dest)
set -e
HERE=$(cd "$(dirname "$0")" && pwd); PKG=$HERE/../dist/material-grub
D=""; RES=""; RUN=1; PKGARG=""
while [ $# -gt 0 ]; do case $1 in --dest) D=$2; shift;; --res) RES=$2; shift;; --pkg) PKGARG=$2; shift;; --no-run) RUN=0;; esac; shift; done
python3 -c "import PIL" 2>/dev/null || echo "WARNING: python3 Pillow missing; the icon rail will be disabled (dnf install python3-pillow)"
[ -n "$PKGARG" ] && PKG=$PKGARG
[ -d "$PKG" ] || { echo "run scripts/package.py first"; exit 1; }
echo "    - copying the theme package to $D/usr/share/material-grub (replacing any older version)"
rm -rf "$D/usr/share/material-grub"
install -d "$D/usr/share/material-grub" "$D/usr/libexec" "$D/etc/grub.d" "$D/etc/systemd/system"
cp -a "$PKG/." "$D/usr/share/material-grub/"
chmod +x "$D/usr/share/material-grub/bin/"*
echo "    - installing GRUB hooks (05_material, 15_material_menu, 90_material_system) and the systemd path unit"
install -m755 "$HERE/postprocess.sh" "$D/usr/libexec/material-grub-postprocess"
install -m755 "$HERE/05_material" "$D/etc/grub.d/05_material"
install -m755 "$HERE/15_material_menu" "$D/etc/grub.d/15_material_menu"
install -m755 "$HERE/90_material_system" "$D/etc/grub.d/90_material_system"
install -m644 "$HERE"/systemd/material-grub.* "$D/etc/systemd/system/"
if [ -z "$D" ]; then
  B=/var/backups/material-grub; mkdir -p "$B"
  [ -f "$B/default-grub.orig" ] || cp -a /etc/default/grub "$B/default-grub.orig"
  for f in /boot/grub2/grub.cfg /boot/grub/grub.cfg; do [ -f "$f" ] && [ ! -f "$B/$(echo $f | tr / _).orig" ] && cp -a "$f" "$B/$(echo $f | tr / _).orig"; done
  echo "    - backups of your GRUB files are in $B"
fi
if [ -n "$RES" ] && [ -z "$D" ]; then
  if grep -q '^GRUB_GFXMODE=' /etc/default/grub; then sed -i "s/^GRUB_GFXMODE=.*/GRUB_GFXMODE=$RES/" /etc/default/grub; else echo "GRUB_GFXMODE=$RES" >> /etc/default/grub; fi
fi
if [ -z "$D" ] && [ $RUN = 1 ]; then
  command -v grub2-editenv >/dev/null && grub2-editenv - unset menu_auto_hide 2>/dev/null || true
  if [ -d /run/systemd/system ] && command -v systemctl >/dev/null; then
    systemctl daemon-reload; systemctl enable --now material-grub.path
  else echo "NOTE: no systemd: re-run the installer after kernel/boot-entry changes."; fi
  CFG=/boot/grub2/grub.cfg; [ -f "$CFG" ] || CFG=/boot/grub/grub.cfg
  MK=$(command -v grub2-mkconfig || command -v grub-mkconfig) || { echo "grub-mkconfig not found"; exit 1; }
  echo "    - regenerating $CFG (this can take up to a minute)"
  "$MK" -o "$CFG"
  echo "    - naming entries, building the Advanced options structure, rendering per-entry scenes"
  /usr/libexec/material-grub-postprocess
fi
echo "installed${D:+ to $D}"
