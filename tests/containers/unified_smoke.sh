#!/bin/sh
# The GRUB part of the unified installer, for real, in a distro container with a fake /boot.   usage: sh unified_smoke.sh debian|fedora
# /src: this repository (read-only), /src/material-boot-core: the core   /out: receives unified-<distro>.txt
# 1. install the core through the unified installer, in a bundle made of the two checkouts
# 2. install GRUB the old way (install.sh), take a snapshot of what it put on the system, remove it
# 3. install GRUB through `material-boot core install --only grub`: the same files must be there (the state record, the backups and the logs aside)
# 4. remove it through `material-boot core install --uninstall --only grub`: grub.cfg must be byte for byte what it was before
set -e
d=$1
R=/out/unified-$d.txt; : > $R
say() { echo "$*" | tee -a $R; }
case $d in
 debian) apt-get update -qq >/dev/null; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq grub-common os-prober python3 python3-pil python3-venv python3-pip librsvg2-bin >/dev/null 2>&1; CFG=/boot/grub/grub.cfg;;
 fedora) dnf install -y -q grub2-tools grub2-tools-extra librsvg2-tools python3 python3-pip python3-pillow >/dev/null 2>&1; CFG=/boot/grub2/grub.cfg;;
esac
mkdir -p "$(dirname $CFG)" /etc/default
for v in 6.8.0-45-generic 6.8.0-40-generic; do touch /boot/vmlinuz-$v /boot/initrd.img-$v; done
for p in /usr/sbin/grub-probe /usr/sbin/grub2-probe; do [ -e $p ] && cp /src/tests/containers/probe $p; done
[ -f /etc/default/grub ] || printf 'GRUB_TIMEOUT=5\nGRUB_DISTRIBUTOR=test\nGRUB_CMDLINE_LINUX="quiet"\nGRUB_GFXMODE=1920x1080\n' > /etc/default/grub
MK=$(command -v grub2-mkconfig || command -v grub-mkconfig); $MK -o $CFG >/dev/null 2>&1
before=$(sha256sum $CFG | cut -d' ' -f1)

# a bundle of the checkouts: the core's library, its scripts, its assets and the shim, and the GRUB part (its manifest and its sources)
cp -a /src /work; B=/bundle; mkdir -p $B/lib $B/parts/grub
C=/work/material-boot-core
cp -a $C/material_boot $B/lib/ && cp $C/VERSION $B/lib/material_boot/VERSION && cp -a $C/scripts $C/assets $C/bin $B/
cp /work/material-boot-part.json $B/parts/grub/manifest.json; ln -s /work/install $B/parts/grub/install
export MATERIAL_LIB=$B/lib
MB="sh $B/bin/material-boot"
snap() { # what is on the system that belongs to GRUB's install, with contents; the state record, backups and logs differ by design
  find /boot /etc/grub.d /etc/default /etc/material-grub* /usr/share/material-grub /usr/libexec /usr/local /usr/lib/systemd /etc/systemd /var/lib/material-grub /usr/share/material-boot/plugins.d \
    -type f 2>/dev/null | grep -v -e '/state.json$' -e '/backups/' -e '\.log$' -e '__pycache__' -e '/last-' | sort | xargs sha256sum 2>/dev/null || true; }

say "== the core, through the unified installer"
$MB core install --bundle $B --only core --yes > /tmp/core.log 2>&1 && say "core install: ok" || { say "core install FAILED"; tail -30 /tmp/core.log | tee -a $R; exit 1; }
[ -x /usr/local/bin/material-boot ] && say "material-boot command installed" || { say "no /usr/local/bin/material-boot"; exit 1; }
git_free_tree=$(ls /usr/share/material-boot) && say "installed: $(echo $git_free_tree | tr '\n' ' ')"

say "== GRUB the old way (install.sh)"
unset MATERIAL_LIB
sh /work/install.sh --yes --no-tui --res 1920x1080 --scheme dark --style rail > /tmp/old.log 2>&1 && say "install.sh: ok" || { say "install.sh FAILED"; tail -40 /tmp/old.log | tee -a $R; exit 1; }
grep -q "classes applied" $CFG && say "grub.cfg annotated" || { say "grub.cfg NOT annotated (install.sh)"; exit 1; }
cp /etc/material-grub.conf /tmp/conf.A; snap > /tmp/A.sum; say "files: $(wc -l < /tmp/A.sum)"
sh /work/install.sh --uninstall --yes > /tmp/unold.log 2>&1 && say "install.sh --uninstall: ok" || { say "install.sh --uninstall FAILED"; tail -30 /tmp/unold.log | tee -a $R; exit 1; }
[ "$(sha256sum $CFG | cut -d' ' -f1)" = "$before" ] && say "grub.cfg restored" || { say "grub.cfg NOT restored by install.sh --uninstall"; exit 1; }

say "== GRUB through material-boot core install --only grub"
$MB core install --bundle $B --only grub --yes --grub-res 1920x1080 --scheme dark --style rail > /tmp/new.log 2>&1 && say "material-boot core install: ok" || { say "material-boot core install FAILED"; tail -60 /tmp/new.log | tee -a $R; exit 1; }
grep -q "classes applied" $CFG && say "grub.cfg annotated" || { say "grub.cfg NOT annotated (unified)"; tail -40 /tmp/new.log | tee -a $R; exit 1; }
snap > /tmp/B.sum
if cmp -s /tmp/A.sum /tmp/B.sum; then say "SAME FILES as install.sh"; else say "DIFFERENT FILES from install.sh"; diff /tmp/A.sum /tmp/B.sum | head -30 | tee -a $R; diff /tmp/conf.A /etc/material-grub.conf | tee -a $R; exit 1; fi
grep -q '"grub"' /var/lib/material-grub/state.json && say "state record names grub" || { say "state record does not name grub"; cat /var/lib/material-grub/state.json | tee -a $R; exit 1; }
$MB core parts | grep -q "grub .*ok" && say "material-boot core parts lists grub as usable" || { say "grub is not a usable part:"; $MB core parts | tee -a $R; exit 1; }
$MB grub version 2>&1 | grep -q "material-grub" && say "material-boot grub version: ok" || { say "material-boot grub version FAILED"; exit 1; }
$MB core doctor > /tmp/doctor.txt 2>&1 && say "core doctor: ok" || { say "core doctor FAILED"; cat /tmp/doctor.txt | tee -a $R; exit 1; }
material-grub doctor > /tmp/doctor2.txt 2>&1 && say "material-grub doctor: ok" || { say "material-grub doctor FAILED"; cat /tmp/doctor2.txt | tee -a $R; exit 1; }

say "== removal through the unified installer"
$MB core install --bundle $B --uninstall --only grub --yes > /tmp/un.log 2>&1 && say "uninstall: ok" || { say "uninstall FAILED"; tail -30 /tmp/un.log | tee -a $R; exit 1; }
[ "$(sha256sum $CFG | cut -d' ' -f1)" = "$before" ] && say "grub.cfg restored" || { say "grub.cfg NOT restored by the unified uninstall"; tail -30 /tmp/un.log | tee -a $R; exit 1; }
grep -q '"grub"' /var/lib/material-grub/state.json 2>/dev/null && { say "state record still names grub"; exit 1; } || say "state record forgot grub"
grep -q '"core"' /var/lib/material-grub/state.json && say "state record still names the core" || { say "the unified uninstall lost the core's entry of the state record"; exit 1; }
[ ! -e /usr/share/material-boot/plugins.d/grub.json ] && say "manifest removed" || { say "plugins.d/grub.json is still there"; exit 1; }
say "ALL OK"
