#!/bin/sh
# A REAL version bump: 1.0.0 -> 1.0.1 through the package manager's ordinary upgrade (no --replacepkgs, no --reinstall), the core already installed.
#   usage: sh release_bump_smoke.sh rpm|deb|arch
# /src: this repository (read-only)   /old: the 1.0.0 package   /pkg: the core's package and the 1.0.1 package   /out: receives bump-<fmt>.txt
# The person's settings must survive, the state record must say the new version, the manifest must be the package's, and everything must still work.
set -e
fmt=$1
R=/out/bump-$fmt.txt; : > $R
say() { echo "$*" | tee -a $R; }
case $fmt in
  rpm)  dnf install -y -q grub2-tools grub2-tools-extra librsvg2-tools python3 python3-pip python3-pillow >/dev/null 2>&1; CFG=/boot/grub2/grub.cfg
        base() { dnf install -y /pkg/material-boot-core-[0-9]*.rpm /old/material-grub-1.0.0-*.rpm; }; up() { dnf install -y /pkg/material-grub-1.0.1-*.rpm; } ;;
  deb)  apt-get update -qq >/dev/null; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq grub-common os-prober python3 python3-pil python3-venv python3-pip librsvg2-bin >/dev/null 2>&1; CFG=/boot/grub/grub.cfg
        base() { DEBIAN_FRONTEND=noninteractive apt-get install -y /pkg/material-boot-core_*.deb /old/material-grub_1.0.0_all.deb; }
        up() { DEBIAN_FRONTEND=noninteractive apt-get install -y -o Dpkg::Options::=--force-confold /pkg/material-grub_1.0.1_all.deb; } ;;
  arch) pacman -Syu --noconfirm --needed grub librsvg python python-pip python-pillow >/dev/null 2>&1; CFG=/boot/grub/grub.cfg
        base() { pacman -U --noconfirm /pkg/material-boot-core-[0-9]*.pkg.tar.* /old/material-grub-1.0.0-*.pkg.tar.*; }; up() { pacman -U --noconfirm /pkg/material-grub-1.0.1-*.pkg.tar.*; } ;;
esac
mkdir -p "$(dirname $CFG)" /etc/default
for v in 6.8.0-45-generic 6.8.0-40-generic; do touch /boot/vmlinuz-$v /boot/initrd.img-$v; done
for p in /usr/sbin/grub-probe /usr/sbin/grub2-probe; do [ -e $p ] && cp /src/tests/containers/probe $p; done
[ -f /etc/default/grub ] || printf 'GRUB_TIMEOUT=5\nGRUB_DISTRIBUTOR=test\nGRUB_CMDLINE_LINUX="quiet"\nGRUB_GFXMODE=1920x1080\n' > /etc/default/grub
MK=$(command -v grub2-mkconfig || command -v grub-mkconfig); $MK -o $CFG >/dev/null 2>&1

say "== 1.0.0 with the core"
base > /tmp/b.log 2>&1 && say "install: ok" || { say "install FAILED"; tail -30 /tmp/b.log | tee -a $R; exit 1; }
material-grub version | grep -q "^material-grub 1.0.0" && say "version 1.0.0" || { say "wrong version"; material-grub version | tee -a $R; exit 1; }
material-grub doctor > /tmp/d0.txt 2>&1 && say "doctor: ok" || { say "doctor FAILED"; cat /tmp/d0.txt | tee -a $R; exit 1; }
material-grub conf STYLE=list >/dev/null; material-grub colour '#7E57C2' --apply > /tmp/c0.log 2>&1 && say "settings made: style list, one seed colour" || { say "colour FAILED"; tail -20 /tmp/c0.log | tee -a $R; exit 1; }
echo "# my own line" >> /etc/material-grub.conf
grep -q '"grub": "1.0.0"' /var/lib/material-grub/state.json && say "record says grub 1.0.0" || { say "record before: $(cat /var/lib/material-grub/state.json)"; exit 1; }

say "== the update to 1.0.1"
up > /tmp/u.log 2>&1 && say "package manager: ok" || { say "package manager FAILED"; tail -40 /tmp/u.log | tee -a $R; exit 1; }
material-grub version | grep -q "^material-grub 1.0.1" && say "version 1.0.1" || { say "version after: $(material-grub version)"; exit 1; }
material-grub doctor > /tmp/d1.txt 2>&1 && say "doctor: ok" || { say "doctor FAILED after the update"; cat /tmp/d1.txt | tee -a $R; exit 1; }
grep -q "^STYLE=list" /etc/material-grub.conf && grep -q "# my own line" /etc/material-grub.conf && say "settings kept (style, own line)" || { say "settings LOST"; exit 1; }
material-grub colour | grep -q "#7E57C2" && say "the seed colour kept" || { say "the seed colour LOST"; exit 1; }
grep -q "classes applied" $CFG && say "grub.cfg annotated" || { say "grub.cfg NOT annotated"; exit 1; }
grep -q '"grub": "1.0.1"' /var/lib/material-grub/state.json && grep -q '"core": "1.0.0"' /var/lib/material-grub/state.json && say "record: grub 1.0.1, core 1.0.0" || { say "record after: $(cat /var/lib/material-grub/state.json)"; exit 1; }
python3 - <<'PY' && say "history: 1.0.0 then 1.0.1" || { say "history wrong"; exit 1; }
import json
h = [x["to"] for x in json.load(open("/var/lib/material-grub/state.json"))["history"]]
assert h[-1] in ("1.0.0", "1.0.1") and "1.0.0" in h, h
PY
[ "$(sed -n 's/.*"version": "\(.*\)".*/\1/p' /usr/share/material-boot/plugins.d/grub.json)" = 1.0.1 ] && say "the manifest says 1.0.1" || { say "manifest version"; cat /usr/share/material-boot/plugins.d/grub.json | tee -a $R; exit 1; }
material-boot core parts | grep -q "grub .*1.0.1.*ok" && say "core parts: grub 1.0.1 ok" || { say "core parts"; material-boot core parts | tee -a $R; exit 1; }
material-grub apply > /tmp/a1.log 2>&1 && say "apply after the update: ok" || { say "apply FAILED"; tail -20 /tmp/a1.log | tee -a $R; exit 1; }
say "ALL OK"
