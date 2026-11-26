#!/bin/sh
# Installs a built package of the core in a distro container and checks what the package manager does with it.   usage: sh pkg_smoke.sh rpm|deb|arch
# /src: the repository (read-only)   /pkg: the directory holding the built package   /out: receives pkg-<fmt>.txt
# 1. install: the dependencies come from the package's own requirements, the shared data is built on the machine, doctor passes
# 2. the command: conf, colour, presets, overrides, a part that plugs in through the package's plugins.d
# 3. a changed scheme: `core apply` rebuilds the data
# 4. upgrade (reinstall): settings and a part's manifest survive
# 5. a broken data build (no rsvg-convert): the package manager must still succeed and the old data stays
# 6. removal: nothing the package generated is left behind
set -e
fmt=$1
R=/out/pkg-$fmt.txt; : > $R
say() { echo "$*" | tee -a $R; }
case $fmt in
  rpm)  inst() { dnf install -y /pkg/material-boot-core-[0-9]*.rpm; }; reinst() { dnf reinstall -y /pkg/material-boot-core-[0-9]*.rpm; }; remove() { dnf remove -y material-boot-core; } ;;
  deb)  apt-get update -qq >/dev/null
        inst() { DEBIAN_FRONTEND=noninteractive apt-get install -y /pkg/material-boot-core_*.deb; }
        reinst() { DEBIAN_FRONTEND=noninteractive apt-get install -y --reinstall /pkg/material-boot-core_*.deb; }
        remove() { DEBIAN_FRONTEND=noninteractive apt-get remove -y material-boot-core; } ;;
  arch) pacman -Syu --noconfirm --needed >/dev/null 2>&1
        inst() { pacman -U --noconfirm /pkg/material-boot-core-[0-9]*.pkg.tar.*; }; reinst() { pacman -U --noconfirm /pkg/material-boot-core-[0-9]*.pkg.tar.*; }; remove() { pacman -R --noconfirm material-boot-core; } ;;
esac
P=/usr/share/material-boot
V=$(cat /src/VERSION)

say "== install"
inst > /tmp/inst.log 2>&1 && say "package manager: ok" || { say "package manager: FAILED"; tail -30 /tmp/inst.log | tee -a $R; exit 1; }
material-boot version | grep -q "^material-boot $V " && say "material-boot version: ok" || { say "material-boot version FAILED"; material-boot version 2>&1 | tee -a $R; exit 1; }
for f in palettes.json classes.json rules.json titles.json subtitles.json scheme.txt glyphs/tux.png fonts/GoogleSansFlex-VF.ttf; do
  [ -e $P/data/$f ] || { say "the shared data was not built: $P/data/$f is missing"; tail -30 /tmp/inst.log | tee -a $R; exit 1; }
done
say "the shared data was built on the machine"
[ "$(cat $P/data/scheme.txt)" = dark ] && say "data scheme: dark (the default)" || { say "data scheme is not dark"; exit 1; }
material-boot core doctor > /tmp/doctor.txt 2>&1 && say "doctor: ok" || { say "doctor: FAILED"; cat /tmp/doctor.txt | tee -a $R; exit 1; }
python3 - <<PY && say "state record: the core, installed as a package" || { say "state record wrong"; cat /var/lib/material-grub/state.json | tee -a $R; exit 1; }
import json
s = json.load(open("/var/lib/material-grub/state.json"))
assert s["parts"]["core"] == "$V" and s["how"] == "package", s
PY
[ -d $P/plugins.d ] && say "plugins.d exists (owned by the package)"

say "== the command"
material-boot help | grep -q "core presets" && say "help lists the core commands: ok" || { say "material-boot help FAILED"; exit 1; }
material-boot core conf STYLE=list >/dev/null && grep -q "^STYLE=list" /etc/material-grub.conf && say "conf STYLE=list: ok" || { say "core conf FAILED"; exit 1; }
material-boot core colour '#7E57C2' > /tmp/colour.log 2>&1 && material-boot core colour | grep -q "#7E57C2" && say "colour: ok" || { say "core colour FAILED"; cat /tmp/colour.log | tee -a $R; exit 1; }
material-boot core overrides check | grep -q "^valid" && say "overrides check: valid" || { say "overrides check FAILED"; exit 1; }
material-boot core presets save smoke >/dev/null && material-boot core presets list | grep -q smoke && say "presets: ok" || { say "presets FAILED"; exit 1; }
material-boot plymouth > /tmp/known.txt 2>&1 || true; grep -q "package: material-plymouth" /tmp/known.txt && say "a known part that is not installed names its package" || { say "known-part message FAILED"; cat /tmp/known.txt | tee -a $R; exit 1; }
printf 'def main(argv, core):\n    print("fake part says", argv)\n    return 3\n' > /usr/share/material-boot/fake_entry.py
printf '{"manifest":2,"name":"fake","title":"Fake","version":"1.0.0","core_api":2,"entry":"%s/fake_entry.py","commands":{"go":"do it"}}' $P > $P/plugins.d/fake.json
rc=0; material-boot fake go || rc=$?; [ "$rc" = 3 ] && say "a part plugs in through plugins.d and its exit status passes through" || { say "part dispatch FAILED (status $rc)"; exit 1; }
material-boot core parts | grep -q "fake" && say "core parts lists it" || { say "core parts FAILED"; exit 1; }

say "== a changed scheme"
material-boot core conf SCHEME=light >/dev/null
material-boot core apply > /tmp/apply.log 2>&1 && say "core apply: ok" || { say "core apply FAILED"; cat /tmp/apply.log | tee -a $R; exit 1; }
grep -q "rebuilt the shared data for the light scheme" /tmp/apply.log && [ "$(cat $P/data/scheme.txt)" = light ] && say "the data was rebuilt for the light scheme" || { say "the data was not rebuilt"; cat /tmp/apply.log | tee -a $R; exit 1; }

say "== upgrade"
echo "STYLE=split" >> /etc/material-grub.conf    # a user edit must survive
reinst > /tmp/up.log 2>&1 && say "package manager: ok" || { say "package manager: FAILED"; tail -30 /tmp/up.log | tee -a $R; exit 1; }
grep -q "^STYLE=split" /etc/material-grub.conf && say "config kept" || { say "config OVERWRITTEN"; exit 1; }
[ -f $P/plugins.d/fake.json ] && say "a part's manifest survives the upgrade" || { say "the part's manifest was removed"; exit 1; }
[ "$(cat $P/data/scheme.txt)" = light ] && say "the data follows the configured scheme after an upgrade" || { say "the data is not for the configured scheme"; exit 1; }
material-boot core doctor >/dev/null 2>&1 && say "doctor after the upgrade: ok" || { say "doctor after the upgrade FAILED"; exit 1; }

say "== a broken data build"
RS=$(command -v rsvg-convert); mv "$RS" "$RS.real"
reinst > /tmp/bad.log 2>&1 && say "package manager: ok even though the data cannot be built" || { say "package manager: FAILED on a failed data build"; tail -30 /tmp/bad.log | tee -a $R; exit 1; }
[ -f $P/data/palettes.json ] && say "the old data is still there" || { say "the old data was lost"; exit 1; }
mv "$RS.real" "$RS"
rm -rf $P/plugins.d/fake.json $P/fake_entry.py $P/__pycache__   # the fake part, with the bytecode python wrote next to it

say "== removal"
remove > /tmp/rm.log 2>&1 && say "package manager: ok" || { say "package manager: FAILED"; tail -30 /tmp/rm.log | tee -a $R; exit 1; }
[ ! -e /usr/bin/material-boot ] && say "the command is gone" || { say "the command is still there"; exit 1; }
[ ! -e $P/data ] && say "the generated data is gone" || { say "the generated data was left behind: $(ls $P)"; exit 1; }
left=$(find $P 2>/dev/null | head -5); [ -z "$left" ] && say "nothing is left in $P" || { say "left behind in $P: $left"; exit 1; }
# no python here: removing the package may have removed python3 with it (dnf removes the dependencies nothing else needs)
[ -f /var/lib/material-grub/state.json ] && ! grep -q '"core"' /var/lib/material-grub/state.json && say "the state record forgot the core" || { say "the state record still lists the core"; cat /var/lib/material-grub/state.json 2>&1 | tee -a $R; exit 1; }
say "ALL OK"
