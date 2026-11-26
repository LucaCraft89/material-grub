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
# material-boot-core: the installed tools import it from /usr/share/material-boot/lib. Its own package comes with G3 (material-grub then requires it); until
# then the checked-out core is copied to where that package would put it.
mkdir -p /usr/share/material-boot/lib && cp -a /src/material-boot-core/material_boot /usr/share/material-boot/lib/ && cp /src/material-boot-core/VERSION /usr/share/material-boot/lib/material_boot/VERSION \
  && find /usr/share/material-boot/lib -name __pycache__ -prune -exec rm -rf {} +
case $fmt in
  rpm)  dnf install -y -q grub2-tools grub2-tools-extra librsvg2-tools python3 python3-pip python3-pillow >/dev/null 2>&1; CFG=/boot/grub2/grub.cfg
        inst() { dnf install -y /pkg/material-grub-[0-9]*.rpm; }; reinst() { dnf reinstall -y /pkg/material-grub-[0-9]*.rpm; }; inst_gui() { dnf install -y /pkg/material-grub-gui-*.rpm; } ;;
  deb)  apt-get update -qq >/dev/null; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq grub-common os-prober python3 python3-pil python3-venv python3-pip librsvg2-bin >/dev/null 2>&1; CFG=/boot/grub/grub.cfg
        inst() { DEBIAN_FRONTEND=noninteractive apt-get install -y /pkg/material-grub_*.deb; }; reinst() { DEBIAN_FRONTEND=noninteractive apt-get install -y --reinstall /pkg/material-grub_*.deb; }; inst_gui() { DEBIAN_FRONTEND=noninteractive apt-get install -y /pkg/material-grub-gui_*.deb; } ;;
  arch) pacman -Syu --noconfirm --needed grub librsvg python python-pip python-pillow >/dev/null 2>&1; CFG=/boot/grub/grub.cfg
        inst() { pacman -U --noconfirm /pkg/material-grub-[0-9]*.pkg.tar.*; }; reinst() { pacman -U --noconfirm /pkg/material-grub-[0-9]*.pkg.tar.*; }; inst_gui() { pacman -U --noconfirm /pkg/material-grub-gui-[0-9]*.pkg.tar.*; } ;;
esac
mkdir -p "$(dirname $CFG)" /etc/default
for v in 6.8.0-45-generic 6.8.0-40-generic; do touch /boot/vmlinuz-$v /boot/initrd.img-$v; done
for p in /usr/sbin/grub-probe /usr/sbin/grub2-probe; do [ -e $p ] && cp /src/tests/containers/probe $p; done
[ -f /etc/default/grub ] || printf 'GRUB_TIMEOUT=5\nGRUB_DISTRIBUTOR=test\nGRUB_CMDLINE_LINUX="quiet"\nGRUB_GFXMODE=1920x1080\n' > /etc/default/grub
MK=$(command -v grub2-mkconfig || command -v grub-mkconfig); $MK -o $CFG >/dev/null 2>&1
before=$(sha256sum $CFG | cut -d' ' -f1)

say "== install"
inst > /tmp/inst.log 2>&1 && say "package manager: ok" || { say "package manager: FAILED"; tail -30 /tmp/inst.log | tee -a $R; exit 1; }
material-grub version | grep -q "^material-grub [0-9]" && say "material-grub version: ok" || { say "material-grub version FAILED"; exit 1; }
material-grub help | grep -q "colour" && say "material-grub help: ok" || { say "material-grub help FAILED"; exit 1; }
material-grub doctor > /tmp/doctor.txt 2>&1 && say "doctor: ok" || { say "doctor: FAILED"; cat /tmp/doctor.txt | tee -a $R; tail -40 /tmp/inst.log | tee -a $R; exit 1; }
grep -q "classes applied" $CFG && say "grub.cfg annotated" || { say "grub.cfg NOT annotated"; exit 1; }
[ -e /etc/material-grub.conf ] && say "config present"
[ -e /usr/share/material-grub-gui/material-grub-gui ] && { say "the GUI was installed with the theme (it must not be)"; exit 1; } || say "the GUI is not installed by the theme package"

say "== features: a style per distro, one seed colour, overrides, the single command"
case $fmt in rpm) ST=split;; deb) ST=list;; *) ST=clean;; esac
material-grub conf STYLE=$ST >/dev/null && grep -q "^STYLE=$ST" /etc/material-grub.conf && say "conf STYLE=$ST: ok" || { say "material-grub conf FAILED"; exit 1; }
material-grub colour '#7E57C2' --apply > /tmp/colour.log 2>&1 && say "colour + apply: ok" || { say "colour --apply FAILED"; tail -20 /tmp/colour.log | tee -a $R; exit 1; }
material-grub colour | grep -q "#7E57C2" && say "colour is recorded" || { say "colour not recorded"; exit 1; }
material-grub overrides check | grep -q "^valid" && say "overrides check: valid" || { say "overrides check FAILED"; exit 1; }
printf '{"version":1,"seed":{"mode":"single","color":"#7E57C2"},"entries":[{"match":{"key":"tux"},"name":"Penguin","color":"#E95420"}]}' > /etc/material-grub/overrides.json
material-grub apply > /tmp/ov.log 2>&1 && say "apply with overrides: ok" || { say "apply with overrides FAILED"; tail -20 /tmp/ov.log | tee -a $R; exit 1; }
material-grub doctor > /tmp/doctor-ov.txt 2>&1 && say "doctor after overrides: ok" || { say "doctor after overrides FAILED"; cat /tmp/doctor-ov.txt | tee -a $R; exit 1; }
grep -q "overrides .*valid" /tmp/doctor-ov.txt && say "doctor sees the overrides" || { say "doctor does not report the overrides"; cat /tmp/doctor-ov.txt | tee -a $R; exit 1; }
material-grub presets save smoke >/dev/null && material-grub presets list | grep -q smoke && say "presets: ok" || { say "presets FAILED"; exit 1; }
material-grub update | grep -q "installed: Material GRUB" && say "update info: ok"
rm -f /etc/material-grub/overrides.json; material-grub conf STYLE=rail >/dev/null

say "== upgrade"
echo "STYLE=list" >> /etc/material-grub.conf    # a user edit must survive
reinst > /tmp/up.log 2>&1 && say "package manager: ok" || { say "package manager: FAILED"; tail -30 /tmp/up.log | tee -a $R; exit 1; }
material-grub doctor > /tmp/doctor2.txt 2>&1 && say "doctor: ok" || { say "doctor: FAILED"; cat /tmp/doctor2.txt | tee -a $R; exit 1; }
grep -q "^STYLE=list" /etc/material-grub.conf && say "config kept" || { say "config OVERWRITTEN"; exit 1; }

say "== optional GUI package"
inst_gui > /tmp/gui.log 2>&1 && say "gui package manager: ok" || { say "gui package manager: FAILED"; tail -30 /tmp/gui.log | tee -a $R; exit 1; }
for f in /usr/share/material-grub-gui/material-grub-gui /usr/libexec/material-grub-gui-helper /usr/share/polkit-1/actions/org.material-grub.gui.policy /usr/share/applications/material-grub-gui.desktop /usr/share/material-grub-gui/web/index.html; do
  [ -e "$f" ] || { say "gui file missing: $f"; exit 1; }
done
material-grub gui --help >/dev/null 2>&1 && say "material-grub gui starts" || { say "material-grub gui --help FAILED"; material-grub gui --help 2>&1 | tail -5 | tee -a $R; exit 1; }
extra=$(ls /usr/local/bin /usr/local/sbin /usr/bin /usr/sbin 2>/dev/null | grep "^material-grub" | sort -u | tr "\n" " ")
[ "$extra" = "material-grub " ] && say "only one command on the PATH: material-grub" || { say "unexpected commands on the PATH: $extra"; exit 1; }
python3 /src/tests/containers/gui_probe.py > /tmp/guiprobe.txt 2>&1 && say "the packaged GUI answers (state, previews in 4 styles, security checks)" || { say "GUI PROBE FAILED"; tail -20 /tmp/guiprobe.txt | tee -a $R; exit 1; }
echo '{"verb":"nope"}' | /usr/libexec/material-grub-gui-helper | grep -q '"event": "error"' && say "helper refuses an unknown request" || { say "helper did not refuse an unknown request"; exit 1; }

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
say "ALL OK"
