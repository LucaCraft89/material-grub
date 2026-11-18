#!/bin/sh
# usage: sudo ./install.sh [--res WxH] [--dest DIR] [--no-run] [--immutable] [--py PYTHON] [--set KEY=value]...   (DESTDIR-style staging with --dest)
#   --py: the Python the installed tools run with (recorded as MATERIAL_PY in /var/lib/material-grub/env); default python3
#   --set: write KEY=value into /etc/material-grub.conf (STYLE, HINTS, COOKIE, LOGO, ...); the file itself is otherwise never overwritten
#   --immutable: ostree/bootc layout. Nothing goes under /usr: package, venv and the postprocess script live in /var/lib/material-grub,
#                hooks are applied directly to the static grub.cfg instead of through grub-mkconfig.
set -e
HERE=$(cd "$(dirname "$0")" && pwd); PKG=$HERE/../dist/material-grub
D=""; RES=""; RUN=1; PKGARG=""; IMM=0; SETS=""; PYARG=""
while [ $# -gt 0 ]; do case $1 in --dest) D=$2; shift;; --res) RES=$2; shift;; --pkg) PKGARG=$2; shift;; --no-run) RUN=0;; --immutable) IMM=1;; --py) PYARG=$2; shift;; --set) SETS="$SETS $2"; shift;; esac; shift; done
[ -n "$PKGARG" ] && PKG=$PKGARG
[ -d "$PKG" ] || { echo "run scripts/package.py first"; exit 1; }

if [ "$IMM" = 1 ]; then
  ST="$D/var/lib/material-grub"; DEST="$ST/pkg"; PY=${PYARG:-python3}
  install -d "$ST" "$D/etc/systemd/system"
  if ! "$PY" -c "import PIL" 2>/dev/null; then
    echo "    - python3 Pillow is not installed and /usr is read-only: creating a venv in $ST/venv (pip, needs network)"
    python3 -m venv "$ST/venv" && "$ST/venv/bin/pip" install --disable-pip-version-check pillow >/dev/null || { echo "could not create the Pillow venv"; exit 1; }
    PY=$ST/venv/bin/python3
  fi
  echo "    - copying the theme package to $DEST (immutable layout: nothing is written under /usr)"
  rm -rf "$DEST"; install -d "$DEST"; cp -a "$PKG/." "$DEST/"; chmod +x "$DEST/bin/"*
  install -m755 "$HERE/postprocess.sh" "$ST/postprocess"
  install -d "$D/usr/local/sbin"; install -m755 "$HERE/material-grub-apply" "$D/usr/local/sbin/material-grub-apply"
  TO=5; [ -f /etc/default/grub ] && TO=$(sed -n 's/^GRUB_TIMEOUT=\([0-9]\{1,\}\).*/\1/p' /etc/default/grub | head -n1); TO=${TO:-5}
  { echo "MATERIAL_PKG=$DEST"; echo "MATERIAL_PY=$PY"; echo "MG_IMMUTABLE=1"; echo "MG_RES=${RES:-1920x1080}"; echo "MG_TIMEOUT=$TO"; } > "$ST/env"
  install -m644 "$HERE"/systemd/immutable/* "$D/etc/systemd/system/"
else
  python3 -c "import PIL" 2>/dev/null || echo "WARNING: python3 Pillow missing; the icon rail will be disabled (dnf install python3-pillow)"
  echo "    - copying the theme package to $D/usr/share/material-grub (replacing any older version)"
  rm -rf "$D/usr/share/material-grub"
  install -d "$D/usr/share/material-grub" "$D/usr/libexec" "$D/etc/grub.d" "$D/etc/systemd/system"
  cp -a "$PKG/." "$D/usr/share/material-grub/"
  chmod +x "$D/usr/share/material-grub/bin/"*
  echo "    - installing GRUB hooks (05_material, 15_material_menu, 90_material_system) and the systemd path unit"
  install -m755 "$HERE/postprocess.sh" "$D/usr/libexec/material-grub-postprocess"
  install -d "$D/usr/local/sbin"; install -m755 "$HERE/material-grub-apply" "$D/usr/local/sbin/material-grub-apply"
  install -m755 "$HERE/05_material" "$D/etc/grub.d/05_material"
  install -m755 "$HERE/15_material_menu" "$D/etc/grub.d/15_material_menu"
  install -m755 "$HERE/90_material_system" "$D/etc/grub.d/90_material_system"
  install -m644 "$HERE"/systemd/material-grub.* "$D/etc/systemd/system/"
  rm -f "$D/var/lib/material-grub/env"
  if [ -n "$PYARG" ]; then install -d "$D/var/lib/material-grub"; echo "MATERIAL_PY=$PYARG" > "$D/var/lib/material-grub/env"; fi
fi
[ -e "$D/etc/material-grub.conf" ] || install -m644 "$HERE/material-grub.conf" "$D/etc/material-grub.conf"     # never overwrite the user's settings
for kv in $SETS; do      # explicit --set choices (installer flags / TUI): replace the sample line or the existing value, else append
  k=${kv%%=*}; v=${kv#*=}; f="$D/etc/material-grub.conf"
  if grep -q "^#\{0,1\}$k=" "$f"; then sed -i "s|^#\{0,1\}$k=.*|$k=$v|" "$f"; else echo "$k=$v" >> "$f"; fi
done
if [ -z "$D" ]; then
  B=/var/backups/material-grub; mkdir -p "$B"
  [ -f "$B/default-grub.orig" ] || { [ -f /etc/default/grub ] && cp -a /etc/default/grub "$B/default-grub.orig" || true; }
  for f in /boot/grub2/grub.cfg /boot/grub/grub.cfg; do [ -f "$f" ] && [ ! -f "$B/$(echo $f | tr / _).orig" ] && cp -a "$f" "$B/$(echo $f | tr / _).orig"; done
  echo "    - backups of your GRUB files are in $B"
fi
if [ "$IMM" = 0 ] && [ -n "$RES" ] && [ -z "$D" ]; then
  if grep -q '^GRUB_GFXMODE=' /etc/default/grub; then sed -i "s/^GRUB_GFXMODE=.*/GRUB_GFXMODE=$RES/" /etc/default/grub; else echo "GRUB_GFXMODE=$RES" >> /etc/default/grub; fi
fi
if [ -z "$D" ] && [ $RUN = 1 ]; then
  command -v grub2-editenv >/dev/null && grub2-editenv - unset menu_auto_hide 2>/dev/null || true
  if [ -d /run/systemd/system ] && command -v systemctl >/dev/null; then
    systemctl daemon-reload; systemctl enable --now material-grub.path
    [ "$IMM" = 1 ] && systemctl enable --now material-grub-finalize.service
  else echo "NOTE: no systemd: re-run the installer after kernel/boot-entry changes."; fi
  if [ "$IMM" = 1 ]; then
    echo "    - modifying the static grub.cfg (an untouched copy is kept in /var/backups/material-grub), naming entries, rendering scenes"
    MG_FORCE=1 sh "$ST/postprocess"
  else
    CFG=/boot/grub2/grub.cfg; [ -f "$CFG" ] || CFG=/boot/grub/grub.cfg
    MK=$(command -v grub2-mkconfig || command -v grub-mkconfig) || { echo "grub-mkconfig not found"; exit 1; }
    echo "    - regenerating $CFG (this can take up to a minute)"
    echo "    - naming entries, building the Advanced options structure, rendering per-entry scenes"
    # grub-mkconfig and the post-processing run under the same lock as the systemd path unit's runs: a run that started earlier must not
    # restore its old snapshot over the grub.cfg written here
    if command -v flock >/dev/null; then
      MG_FORCE=1 MG_LOCKED=1 flock /run/material-grub.lock sh -c '"$1" -o "$2" && /usr/libexec/material-grub-postprocess' sh "$MK" "$CFG"
    else
      "$MK" -o "$CFG" && MG_FORCE=1 /usr/libexec/material-grub-postprocess
    fi
  fi
fi
echo "installed${D:+ to $D}"
