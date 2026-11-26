#!/bin/sh
# Installs GRUB through `material-boot core install` (the unified installer, from a bundle) in a Fedora container with a fake /boot, then exports what a
# machine would boot from as a tree that scripts/qemu_tree.py can put on a virtual ESP: the grub.cfg the installer wrote, the theme it installed, the BLS
# entries and the font GRUB loads. usage: sh installed_tree.sh   BUNDLE (default /bundle): the unpacked bundle   SRC (default /src): this repository   OUT (default /out): receives tree/
# It changes the machine it runs on (a throw-away container).
# Only what cannot exist in a container is replaced: the fake root device (a made-up UUID that `search` could not find in the VM) is dropped, and the paths
# say /boot/grub instead of Fedora's /boot/grub2 (the ESP of qemu_tree.py is laid out that way).
set -e
BUNDLE=${BUNDLE:-/bundle}; SRC=${SRC:-/src}; OUT=${OUT:-/out}
[ -n "${MG_CA:-}" ] && { cp "$MG_CA" /etc/pki/ca-trust/source/anchors/mg-ca.crt; update-ca-trust; }
dnf -y install -q grub2-tools grub2-tools-extra librsvg2-tools python3 python3-pip python3-pillow >/dev/null 2>&1
mkdir -p /boot/grub2 /boot/loader/entries /etc/default /etc/grub.d
for v in 7.3.3-200 7.2.11-200; do
  touch /boot/vmlinuz-$v.fc44.x86_64 /boot/initramfs-$v.fc44.x86_64.img
  printf 'title Fedora Linux (%s.fc44.x86_64) 44 (Workstation Edition)\nversion %s.fc44.x86_64\nlinux /vmlinuz-%s.fc44.x86_64\ninitrd /initramfs-%s.fc44.x86_64.img\noptions root=UUID=x ro\ngrub_class fedora\n' $v $v $v $v > /boot/loader/entries/abc-$v.fc44.x86_64.conf
done
cp "$SRC/tests/containers/probe" /usr/sbin/grub2-probe
printf 'GRUB_TIMEOUT=120\nGRUB_DISTRIBUTOR=Fedora\nGRUB_ENABLE_BLSCFG=true\nGRUB_GFXMODE=1920x1080\n' > /etc/default/grub
cat > /etc/grub.d/40_custom <<'X'
#!/bin/sh
cat <<'Y'
menuentry 'Windows Boot Manager (on /dev/nvme0n1p1)' --class windows --class os { true }
menuentry 'Arch Linux' --class arch --class gnu-linux --class gnu --class os { true }
menuentry 'UEFI Firmware Settings' --class efi { true }
Y
X
chmod +x /etc/grub.d/40_custom
grub2-mkconfig -o /boot/grub2/grub.cfg >/dev/null 2>&1
cp -r "$BUNDLE" /b; cd /b
sh install.sh --yes --grub-res 1920x1080 --style rail > /tmp/i.log 2>&1 || { tail -40 /tmp/i.log; exit 1; }
grep -q "classes applied" /boot/grub2/grub.cfg || { echo "the installer did not annotate grub.cfg"; exit 1; }
rm -rf "$OUT/tree"; mkdir -p "$OUT/tree/boot/grub/fonts"
cp -a /boot/loader "$OUT/tree/loader"
OUT=$OUT python3 - <<'PY'
import os, re
s = open("/boot/grub2/grub.cfg").read().replace("/boot/grub2", "/boot/grub")
s = re.sub(r"^set (root|boot)='\(hd[^']*'\n", "", s, flags=re.M)     # the fake root device
s = re.sub(r"^\s+search --no-floppy .*$", "  true", s, flags=re.M)     # its search by a made-up UUID
open(os.environ["OUT"] + "/tree/boot/grub/grub.cfg", "w").write(s)
PY
cp -a /boot/grub2/themes "$OUT/tree/boot/grub/themes"
cp /usr/share/grub/unicode.pf2 "$OUT/tree/boot/grub/fonts/" 2>/dev/null || cp /usr/share/grub2/unicode.pf2 "$OUT/tree/boot/grub/fonts/"
cp /boot/grub2/grubenv "$OUT/tree/boot/grub/" 2>/dev/null || true
echo "tree written: $(du -sh "$OUT/tree" | cut -f1)"
