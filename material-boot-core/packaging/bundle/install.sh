#!/bin/sh
# Material Boot: install from this bundle.
#
#   sudo ./install.sh                         what is installed already is updated; on a fresh system: the core and the default parts (GRUB)
#   sudo ./install.sh --with plymouth         also the Plymouth boot splash (--without PART leaves one out, --only PART does just that one)
#   ./install.sh --dry-run                    what would change, nothing is touched (no root needed)
#   sudo ./install.sh --uninstall [--only PART]
#   options of the installer and of every part: ./install.sh --help
#
# This file only finds a Python 3.9+ and checks the bundle; the installer is material_boot/installer.py (docs/installer.md).
#   --no-verify   skip the SHA256SUMS check          (everything else is the installer's own)
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)

verify=1; need_root=1
for a in "$@"; do
  case $a in
    --no-verify) verify=0 ;;
    --dry-run|-h|--help|--root|--root=*) need_root=0 ;;
  esac
done
# the options of the bootstrap are not the installer's
if [ "$verify" = 0 ]; then
  for a in "$@"; do shift; [ "$a" = "--no-verify" ] || set -- "$@" "$a"; done
fi

if [ "$verify" = 1 ] && [ -f "$HERE/SHA256SUMS" ]; then
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$HERE" && sha256sum -c --quiet SHA256SUMS) || { echo "install.sh: this bundle does not match its SHA256SUMS: download it again (or --no-verify)" >&2; exit 1; }
  elif command -v shasum >/dev/null 2>&1; then
    (cd "$HERE" && shasum -a 256 -c --quiet SHA256SUMS) || { echo "install.sh: this bundle does not match its SHA256SUMS: download it again (or --no-verify)" >&2; exit 1; }
  else
    echo "install.sh: no sha256sum or shasum: the bundle was not verified" >&2
  fi
fi

PY=
for c in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then PY=$c; break; fi
done
if [ -z "$PY" ]; then
  cat >&2 <<'MSG'
install.sh: Python 3.9 or newer is needed and none was found. Install it with your package manager, then run this again:
    Fedora/RHEL:   sudo dnf install python3.11        Debian/Ubuntu: sudo apt install python3
    Arch:          sudo pacman -S python              openSUSE:      sudo zypper install python311
    Alpine:        sudo apk add python3               Void:          sudo xbps-install python3
MSG
  exit 1
fi

# installing writes /usr and /etc: ask sudo here, because there is no `material-boot` command to ask again yet
if [ "$need_root" = 1 ] && [ "$(id -u)" != 0 ]; then
  if command -v sudo >/dev/null 2>&1; then
    echo "(this needs root: asking sudo)" >&2
    exec sudo "$HERE/install.sh" "$@"
  fi
  echo "install.sh: this needs root: run it as root" >&2
  exit 1
fi

PYTHONPATH="$HERE/lib${PYTHONPATH:+:$PYTHONPATH}" exec "$PY" -m material_boot core install --bundle "$HERE" "$@"
