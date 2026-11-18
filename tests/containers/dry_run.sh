#!/bin/sh
# Runs inside a distro container (see .github/workflows/ci.yml and tests/containers/README.md):
#   sh dry_run.sh DISTRO       DISTRO: debian | fedora
# Prepares a fake /boot and a stub grub-probe, then runs `install.sh --dry-run` from /src and proves that nothing on the system changed.
# /src is the repository (read-only), /src/dist/material-grub the built package, /out receives the report.
set -e
d=$1
case $d in
 debian) apt-get update -qq >/dev/null; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq grub-common os-prober python3 python3-pil >/dev/null 2>&1;;
 fedora) dnf install -y -q grub2-tools grub2-tools-extra python3 python3-pillow >/dev/null 2>&1;;
esac
mkdir -p /boot/grub /boot/grub2 /etc/default
for v in 6.8.0-45-generic 6.8.0-40-generic; do touch /boot/vmlinuz-$v /boot/initrd.img-$v; done
if [ "$d" = fedora ]; then
  mkdir -p /boot/loader/entries
  for v in 6.12.1-200.fc44.x86_64 6.11.9-300.fc44.x86_64; do
    printf 'title Fedora Linux (%s) 44 (Workstation Edition)\nversion %s\nlinux /vmlinuz-%s\ninitrd /initramfs-%s.img\noptions root=UUID=1 ro\ngrub_class fedora\n' "$v" "$v" "$v" "$v" > /boot/loader/entries/abc-$v.conf
  done
fi
for p in /usr/sbin/grub-probe /usr/sbin/grub2-probe; do [ -e $p ] && cp /src/tests/containers/probe $p; done
[ -f /etc/default/grub ] || printf 'GRUB_TIMEOUT=5\nGRUB_DISTRIBUTOR=test\nGRUB_CMDLINE_LINUX="quiet"\n' > /etc/default/grub
MK=$(command -v grub2-mkconfig || command -v grub-mkconfig)
CFG=/boot/grub/grub.cfg; [ "$d" = fedora ] && CFG=/boot/grub2/grub.cfg
$MK -o $CFG >/dev/null 2>&1
snap() { find /boot /etc /usr/share /usr/libexec /usr/local /var/lib /var/backups -type f 2>/dev/null | sort | xargs sha256sum 2>/dev/null; }
snap > /tmp/before.sum
cp -r /src /work
rc=0
sh /work/install.sh --dry-run --pkg /work/dist/material-grub --res 1920x1080 --yes --no-tui > /out/dry-$d.txt 2>&1 || rc=$?
echo "exit: $rc" >> /out/dry-$d.txt
snap > /tmp/after.sum
if cmp -s /tmp/before.sum /tmp/after.sum; then echo "SYSTEM UNCHANGED" >> /out/dry-$d.txt
else echo "SYSTEM CHANGED" >> /out/dry-$d.txt; diff /tmp/before.sum /tmp/after.sum >> /out/dry-$d.txt || true; fi
