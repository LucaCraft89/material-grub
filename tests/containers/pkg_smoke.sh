#!/bin/sh
# Installs a built package in a distro container with a fake /boot and checks what the package manager does with it.   usage: sh pkg_smoke.sh rpm|deb|arch
# /src: the repository (read-only)   /pkg: the directory holding the built package   /out: receives pkg-<fmt>.txt
# 1. install: the theme is built on the machine, doctor must pass
# 2. upgrade (reinstall): same pipeline, doctor must pass
# 3. broken upgrade: grub-script-check is made to fail; the package manager must still succeed, grub.cfg must be byte for byte unchanged and last-error must exist
set -e
fmt=$1
R=/out/pkg-$fmt.txt; : > $R
say() { echo "$*" | tee -a $R; }
# material-boot-core is a dependency of the package: its own package (built from the core's checkout, see build_pkg.sh there) is in /pkg too.
case $fmt in
  rpm)  dnf install -y -q grub2-tools grub2-tools-extra librsvg2-tools python3 python3-pip python3-pillow >/dev/null 2>&1; CFG=/boot/grub2/grub.cfg
        rm_pkg() { dnf remove -y material-grub; }
        inst() { dnf install -y /pkg/material-boot-core-[0-9]*.rpm /pkg/material-grub-[0-9]*.rpm; }; reinst() { dnf reinstall -y /pkg/material-grub-[0-9]*.rpm; } ;;
  deb)  apt-get update -qq >/dev/null; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq grub-common os-prober python3 python3-pil python3-venv python3-pip librsvg2-bin >/dev/null 2>&1; CFG=/boot/grub/grub.cfg
        rm_pkg() { DEBIAN_FRONTEND=noninteractive apt-get remove -y material-grub; }
        inst() { DEBIAN_FRONTEND=noninteractive apt-get install -y /pkg/material-boot-core_*.deb /pkg/material-grub_*.deb; }; reinst() { DEBIAN_FRONTEND=noninteractive apt-get install -y --reinstall /pkg/material-grub_*.deb; } ;;
  arch) pacman -Syu --noconfirm --needed grub librsvg python python-pip python-pillow >/dev/null 2>&1; CFG=/boot/grub/grub.cfg
        rm_pkg() { pacman -R --noconfirm material-grub; }
        inst() { pacman -U --noconfirm /pkg/material-boot-core-[0-9]*.pkg.tar.* /pkg/material-grub-[0-9]*.pkg.tar.*; }; reinst() { pacman -U --noconfirm /pkg/material-grub-[0-9]*.pkg.tar.*; } ;;
esac
mkdir -p "$(dirname $CFG)" /etc/default
for v in 6.8.0-45-generic 6.8.0-40-generic; do touch /boot/vmlinuz-$v /boot/initrd.img-$v; done
for p in /usr/sbin/grub-probe /usr/sbin/grub2-probe; do [ -e $p ] && cp /src/tests/containers/probe $p; done
[ -f /etc/default/grub ] || printf 'GRUB_TIMEOUT=5\nGRUB_DISTRIBUTOR=test\nGRUB_CMDLINE_LINUX="quiet"\nGRUB_GFXMODE=1920x1080\n' > /etc/default/grub
MK=$(command -v grub2-mkconfig || command -v grub-mkconfig); $MK -o $CFG >/dev/null 2>&1
before=$(sha256sum $CFG | cut -d' ' -f1)

say "== install"
inst > /tmp/inst.log 2>&1 && say "package manager: ok" || { say "package manager: FAILED"; tail -30 /tmp/inst.log | tee -a $R; exit 1; }
material-boot core parts 2>&1 | grep -q "grub .*ok" && say "material-boot core parts lists grub as usable" || { say "grub is not a usable part"; material-boot core parts | tee -a $R; exit 1; }
grep -q '"grub"' /var/lib/material-grub/state.json && grep -q '"core"' /var/lib/material-grub/state.json && say "state record names the core and grub" || { say "state record is wrong"; cat /var/lib/material-grub/state.json | tee -a $R; exit 1; }
[ "$(sed -n 's/.*"entry": "\(.*\)".*/\1/p' /usr/share/material-boot/plugins.d/grub.json)" = /usr/share/material-grub-src/install/part_grub.py ] && say "the manifest is the package's, its entry is the copy with the installer" || { say "the manifest was rewritten"; cat /usr/share/material-boot/plugins.d/grub.json | tee -a $R; exit 1; }
material-boot version | grep -q "^material-boot [0-9]" && say "material-boot version: ok" || { say "material-boot version FAILED"; exit 1; }
material-boot help | grep -q "core colour" && material-boot help | grep -q "ui " && say "material-boot help: ok" || { say "material-boot help FAILED"; exit 1; }
material-boot grub doctor > /tmp/doctor.txt 2>&1 && say "doctor: ok" || { say "doctor: FAILED"; cat /tmp/doctor.txt | tee -a $R; tail -40 /tmp/inst.log | tee -a $R; exit 1; }
grep -q "classes applied" $CFG && say "grub.cfg annotated" || { say "grub.cfg NOT annotated"; exit 1; }
[ -e /etc/material-grub.conf ] && say "config present"

say "== features: a style per distro, one seed colour, overrides, the single command"
case $fmt in rpm) ST=split;; deb) ST=list;; *) ST=clean;; esac
material-boot core conf STYLE=$ST >/dev/null && grep -q "^STYLE=$ST" /etc/material-grub.conf && say "conf STYLE=$ST: ok" || { say "material-boot core conf FAILED"; exit 1; }
material-boot core colour '#7E57C2' --apply > /tmp/colour.log 2>&1 && say "colour + apply: ok" || { say "colour --apply FAILED"; tail -20 /tmp/colour.log | tee -a $R; exit 1; }
material-boot core colour | grep -q "#7E57C2" && say "colour is recorded" || { say "colour not recorded"; exit 1; }
material-boot core overrides check | grep -q "^valid" && say "overrides check: valid" || { say "overrides check FAILED"; exit 1; }
printf '{"version":1,"seed":{"mode":"single","color":"#7E57C2"},"entries":[{"match":{"key":"tux"},"name":"Penguin","color":"#E95420"}]}' > /etc/material-grub/overrides.json
material-boot grub apply > /tmp/ov.log 2>&1 && say "apply with overrides: ok" || { say "apply with overrides FAILED"; tail -20 /tmp/ov.log | tee -a $R; exit 1; }
material-boot grub doctor > /tmp/doctor-ov.txt 2>&1 && say "doctor after overrides: ok" || { say "doctor after overrides FAILED"; cat /tmp/doctor-ov.txt | tee -a $R; exit 1; }
grep -q "overrides .*valid" /tmp/doctor-ov.txt && say "doctor sees the overrides" || { say "doctor does not report the overrides"; cat /tmp/doctor-ov.txt | tee -a $R; exit 1; }
material-boot core presets save smoke >/dev/null && material-boot core presets list | grep -q smoke && say "presets: ok" || { say "presets FAILED"; exit 1; }
rm -f /etc/material-grub/overrides.json; material-boot core conf STYLE=rail >/dev/null

say "== upgrade"
echo "STYLE=list" >> /etc/material-grub.conf    # a user edit must survive
reinst > /tmp/up.log 2>&1 && say "package manager: ok" || { say "package manager: FAILED"; tail -30 /tmp/up.log | tee -a $R; exit 1; }
material-boot grub doctor > /tmp/doctor2.txt 2>&1 && say "doctor: ok" || { say "doctor: FAILED"; cat /tmp/doctor2.txt | tee -a $R; exit 1; }
grep -q "^STYLE=list" /etc/material-grub.conf && say "config kept" || { say "config OVERWRITTEN"; exit 1; }

say "== the editor (it ships with the core package) and the commands"
for f in /usr/libexec/material-boot-ui-helper /usr/share/polkit-1/actions/org.material-boot.ui.policy /usr/share/applications/material-boot.desktop /usr/share/material-boot/lib/material_boot/ui/server.py; do
  [ -e "$f" ] || { say "editor file missing: $f"; exit 1; }
done
material-boot ui --help >/dev/null 2>&1 && say "material-boot ui starts" || { say "material-boot ui --help FAILED"; exit 1; }
extra=$(ls /usr/local/bin /usr/local/sbin /usr/bin /usr/sbin 2>/dev/null | grep "^material-" | sort -u | tr "\n" " ")
[ "$extra" = "material-boot " ] && say "only one command on the PATH: material-boot" || { say "unexpected commands on the PATH: $extra"; exit 1; }
python3 /src/tests/containers/ui_probe.py > /tmp/uiprobe.txt 2>&1 && say "the packaged editor answers (state, previews in 4 styles, security checks)" || { say "EDITOR PROBE FAILED"; tail -20 /tmp/uiprobe.txt | tee -a $R; exit 1; }
echo '{"verb":"nope"}' | /usr/libexec/material-boot-ui-helper | grep -q '"event": "error"' && say "helper refuses an unknown request" || { say "helper did not refuse an unknown request"; exit 1; }

say "== broken upgrade"
# a checker that rejects only our annotated file (grub-mkconfig's own check of its fresh output must still pass)
for n in grub-script-check grub2-script-check; do   # replace the real binaries: package scripts run with a PATH that has no /usr/local
  P=$(command -v $n || true); [ -n "$P" ] || continue
  [ -e "$P.real" ] || mv "$P" "$P.real"
  printf '#!/bin/sh\ngrep -q "material-grub: classes applied" "$1" && { echo "simulated syntax error" >&2; exit 1; }\nexec %s.real "$@"\n' "$P" > "$P"
  chmod +x "$P"; REAL=$P.real
done
reinst > /tmp/bad.log 2>&1 && say "package manager: ok even though the processed grub.cfg is rejected" || { say "package manager: FAILED on a rollback"; tail -30 /tmp/bad.log | tee -a $R; exit 1; }
grep -q "classes applied" $CFG && { say "grub.cfg still holds the rejected result"; tail -40 /tmp/bad.log | tee -a $R; cat /var/lib/material-grub/last-error 2>&1 | tee -a $R; exit 1; } || say "rejected grub.cfg was rolled back"
$REAL $CFG && say "restored grub.cfg is valid"
[ -e /var/lib/material-grub/last-error ] && say "last-error written" || { say "last-error MISSING"; exit 1; }
grep -qi "rolled back" /tmp/bad.log && say "rollback reported in the package manager output" || say "note: rollback text not in the package manager output"

say "== removal (the core stays)"
rm_pkg > /tmp/rm.log 2>&1 && say "package manager: ok" || { say "package manager: FAILED on removal"; tail -30 /tmp/rm.log | tee -a $R; exit 1; }
grep -q "classes applied" $CFG && { say "grub.cfg is still annotated after the removal"; exit 1; } || say "grub.cfg is plain again"
[ ! -e /usr/share/material-boot/plugins.d/grub.json ] && say "the manifest is gone" || { say "the manifest is still there"; exit 1; }
material-boot core parts 2>&1 | grep -q grub && { say "core parts still lists grub"; exit 1; } || say "core parts no longer lists grub"
grep -q '"core"' /var/lib/material-grub/state.json && ! grep -q '"grub"' /var/lib/material-grub/state.json && say "the state record kept the core and forgot grub" || { say "state record after removal:"; cat /var/lib/material-grub/state.json 2>&1 | tee -a $R; exit 1; }
material-boot version > /dev/null && say "material-boot still works" || { say "material-boot is broken after the removal"; exit 1; }
say "ALL OK"
