#!/bin/sh
# An update from a released package (0.7.x: no core, no manifest) to the new packages (which need the core).   usage: sh upgrade_smoke.sh rpm|deb|arch
# /src: this repository (read-only)   /old: the packages built from the released version   /pkg: the new packages and the core's   /out: receives upgrade-<fmt>.txt
# The person's settings must survive, the dependency must pull the core in, the part must be registered and recorded, and everything must still work.
set -e
fmt=$1
R=/out/upgrade-$fmt.txt; : > $R
say() { echo "$*" | tee -a $R; }
case $fmt in
  rpm)  dnf install -y -q grub2-tools grub2-tools-extra librsvg2-tools python3 python3-pip python3-pillow >/dev/null 2>&1; CFG=/boot/grub2/grub.cfg
        old() { dnf install -y /old/material-grub-[0-9]*.rpm; }
        # rpm itself (the version is the same here: a bump is the release's; --replacepkgs makes the same-version package an update, and rpm checks the dependencies)
        new() { rpm -U --nosignature --replacepkgs /pkg/material-boot-core-[0-9]*.rpm /pkg/material-grub-[0-9]*.rpm; }
        new_without_core_in_the_command() { rpm -U --nosignature --replacepkgs /pkg/material-grub-[0-9]*.rpm; } ;;
  deb)  apt-get update -qq >/dev/null; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq grub-common os-prober python3 python3-pil python3-venv python3-pip librsvg2-bin >/dev/null 2>&1; CFG=/boot/grub/grub.cfg
        old() { DEBIAN_FRONTEND=noninteractive apt-get install -y /old/material-grub_*.deb; }
        # the person edited the configuration file: a real update asks which to keep; here the answer is "keep mine"
        new() { DEBIAN_FRONTEND=noninteractive apt-get install -y -o Dpkg::Options::=--force-confold --reinstall /pkg/material-boot-core_*.deb /pkg/material-grub_*.deb; }
        new_without_core_in_the_command() { DEBIAN_FRONTEND=noninteractive apt-get install -y -o Dpkg::Options::=--force-confold --reinstall /pkg/material-grub_*.deb; } ;;
  arch) pacman -Syu --noconfirm --needed grub librsvg python python-pip python-pillow >/dev/null 2>&1; CFG=/boot/grub/grub.cfg
        old() { pacman -U --noconfirm /old/material-grub-[0-9]*.pkg.tar.*; }; new() { pacman -U --noconfirm /pkg/material-boot-core-[0-9]*.pkg.tar.* /pkg/material-grub-[0-9]*.pkg.tar.*; }
        new_without_core_in_the_command() { pacman -U --noconfirm /pkg/material-grub-[0-9]*.pkg.tar.*; } ;;
esac
mkdir -p "$(dirname $CFG)" /etc/default
for v in 6.8.0-45-generic 6.8.0-40-generic; do touch /boot/vmlinuz-$v /boot/initrd.img-$v; done
for p in /usr/sbin/grub-probe /usr/sbin/grub2-probe; do [ -e $p ] && cp /src/tests/containers/probe $p; done
[ -f /etc/default/grub ] || printf 'GRUB_TIMEOUT=5\nGRUB_DISTRIBUTOR=test\nGRUB_CMDLINE_LINUX="quiet"\nGRUB_GFXMODE=1920x1080\n' > /etc/default/grub
MK=$(command -v grub2-mkconfig || command -v grub-mkconfig); $MK -o $CFG >/dev/null 2>&1

say "== the released package, alone"
old > /tmp/old.log 2>&1 && say "install: ok" || { say "install FAILED"; tail -30 /tmp/old.log | tee -a $R; exit 1; }
material-grub doctor > /tmp/d0.txt 2>&1 && say "doctor: ok" || { say "doctor FAILED"; cat /tmp/d0.txt | tee -a $R; exit 1; }
command -v material-boot >/dev/null 2>&1 && { say "material-boot exists before the update"; exit 1; } || say "no material-boot yet"
material-grub conf STYLE=list >/dev/null; material-grub colour '#7E57C2' --apply > /tmp/c0.log 2>&1 && say "settings made: style list, one seed colour" || { say "colour FAILED"; tail -20 /tmp/c0.log | tee -a $R; exit 1; }
echo "# my own line" >> /etc/material-grub.conf

say "== the new GRUB package alone cannot be installed without the core"
new_without_core_in_the_command > /tmp/nocore.log 2>&1 && { say "the package installed without its dependency"; exit 1; } || say "refused: it needs material-boot-core"

say "== the update (GRUB and the core in one transaction)"
new > /tmp/new.log 2>&1 && say "package manager: ok" || { say "package manager FAILED"; tail -40 /tmp/new.log | tee -a $R; exit 1; }
material-boot grub doctor > /tmp/d1.txt 2>&1 && say "doctor: ok" || { say "doctor FAILED after the update"; cat /tmp/d1.txt | tee -a $R; tail -30 /tmp/new.log | tee -a $R; exit 1; }
grep -q "^STYLE=list" /etc/material-grub.conf && grep -q "# my own line" /etc/material-grub.conf && say "settings kept (style, own line)" || { say "settings LOST"; cat /etc/material-grub.conf | tee -a $R; exit 1; }
material-boot core colour | grep -q "#7E57C2" && say "the seed colour kept" || { say "the seed colour LOST"; exit 1; }
grep -q "classes applied" $CFG && say "grub.cfg annotated" || { say "grub.cfg NOT annotated"; exit 1; }
[ ! -e /usr/local/bin/material-grub ] && ! command -v material-grub >/dev/null 2>&1 && say "the old material-grub command is gone" || { say "the old material-grub command is still there"; ls -l /usr/local/bin | tee -a $R; exit 1; }
material-boot core parts | grep -q "grub .*ok" && say "material-boot core parts lists grub" || { say "grub is not a part"; material-boot core parts | tee -a $R; exit 1; }
grep -q '"core"' /var/lib/material-grub/state.json && grep -q '"grub"' /var/lib/material-grub/state.json && say "state record names the core and grub" || { say "state record is wrong"; cat /var/lib/material-grub/state.json | tee -a $R; exit 1; }
material-boot core conf | grep -q "STYLE=list" && say "the core reads the same settings" || { say "the core does not see STYLE=list"; material-boot core conf | tee -a $R; exit 1; }
material-boot grub apply > /tmp/a1.log 2>&1 && say "apply after the update: ok" || { say "apply FAILED"; tail -20 /tmp/a1.log | tee -a $R; exit 1; }
say "ALL OK"
