#!/bin/sh
# Material GRUB: one-command installer for Linux (Fedora/RHEL, Debian/Ubuntu, Arch, openSUSE, Alpine, Void).
#
#   sudo ./install.sh                 # auto-detects resolution, installs missing dependencies, builds and installs
#   sudo ./install.sh --res 1920x1200 # force a resolution
#   sudo ./install.sh --scheme light  # light Material 3 scheme instead of the default dark one
#   sudo ./install.sh --style list    # rail (default) | clean | list      --no-hints  no key-hint pills      --no-cookie / --no-logo  hide the cookie / only the firmware logo
#   sudo ./install.sh                 # in a terminal, missing choices (resolution, style, scheme, ...) are asked in a TUI; --no-tui or --yes skips it, --tui forces it
#   sudo ./install.sh --uninstall
#   ./install.sh --ventoy [MOUNTPOINT]   # theme a Ventoy USB stick instead (no root needed; a TUI picks the stick when no path is given)
#        --res A,B,C  themes for several screen sizes (the first is Ventoy's start mode)    --mode dynamic|snapshot  (default dynamic: follows the ISOs on the stick)
#        ./install.sh --uninstall --ventoy MOUNTPOINT   removes it from the stick again
#   Runtime options (STYLE, HINTS, COOKIE, LOGO) go to /etc/material-grub.conf and can be changed later without rebuilding: sudo material-grub-apply
#   options: --no-deps  never touch the package manager     --stage-only  build only, do not touch GRUB
#            --keep-build  keep the temporary build dir     --force  ignore the NixOS check
#            --immutable  use the ostree/bootc layout (automatic when /run/ostree-booted exists)   --yes  do not ask for confirmation
#            --pkg DIR  install a package built elsewhere   --dist-out DIR  with --stage-only: copy the built package to DIR
#            --preview  render your boot entries with the chosen style as a web page; no root, nothing installed, no VM
#            --dry-run  build in a scratch directory and show a diff of grub.cfg and /etc/default/grub plus the files it would write; changes nothing (needs sudo for the grub.cfg part)
#            --progress json  machine-readable output for the GUI: one JSON object per line (step, info, ok, warn, error, progress, log, done); never asks anything
#   The logic is install/installer.py (Python 3.8+, standard library only); this file finds a Python 3.8+ (installing one with the
#   distribution's package manager when needed, which takes root) and hands over.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)

# --help needs no Python
for a in "$@"; do
  case $a in -h|--help) sed -n 2,20p "$0" | sed 's/^# \{0,1\}//'; exit 0;; esac
done

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

# A Python 3.8 or newer: $MG_INSTALLER_PY, else python3, else the versioned names.
py_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; }
find_python() {
  for c in "${MG_INSTALLER_PY:-}" python3 python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 python3.8; do
    [ -n "$c" ] || continue
    command -v "$c" >/dev/null 2>&1 && py_ok "$c" && { command -v "$c"; return 0; }
  done
  return 1
}

PY=$(find_python) || PY=""
if [ -z "$PY" ]; then
  [ "$(id -u)" -eq 0 ] || die "Python 3.8 or newer is needed and could not be found; run with sudo so the installer can install it: sudo ./install.sh"
  PM=""
  for p in dnf apt-get pacman zypper apk xbps-install; do command -v "$p" >/dev/null 2>&1 && { PM=$p; break; }; done
  [ -n "$PM" ] || die "Python 3.8 or newer is needed and no supported package manager was found (dnf, apt, pacman, zypper, apk, xbps). Install Python 3.8+ and run again."
  # candidates in order: the plain name first, then versioned packages (RHEL 8 family ships Python 3.6 as python3)
  case $PM in
    dnf)          PKGS="python3 python3.12 python3.11 python39 python3.9" ;;
    apt-get)      PKGS="python3 python3.9 python3.10"; apt-get update || true ;;
    pacman)       PKGS="python" ;;
    zypper)       PKGS="python3 python311 python310 python39" ;;
    apk)          PKGS="python3" ;;
    xbps-install) PKGS="python3" ;;
  esac
  for pkg in $PKGS; do
    printf 'Python 3.8+ not found: installing %s with %s ...\n' "$pkg" "$PM"
    case $PM in
      dnf)          dnf install -y "$pkg" || true ;;
      apt-get)      DEBIAN_FRONTEND=noninteractive apt-get install -y "$pkg" || true ;;
      pacman)       pacman -Syu --needed --noconfirm "$pkg" || true ;;
      zypper)       zypper --non-interactive install "$pkg" || true ;;
      apk)          apk add "$pkg" || true ;;
      xbps-install) xbps-install -Sy "$pkg" || true ;;
    esac
    PY=$(find_python) && break
    PY=""
  done
  [ -n "$PY" ] || die "could not install a Python 3.8 or newer with $PM. Install one by hand and run again."
fi
exec "$PY" "$HERE/install/installer.py" "$@"
