#!/bin/sh
# Material GRUB: one-command installer for Linux (Fedora/RHEL, Debian/Ubuntu, Arch, openSUSE, Alpine, Void).
#
#   sudo ./install.sh                 # auto-detects resolution, installs missing dependencies, builds and installs
#   sudo ./install.sh --res 1920x1200 # force a resolution
#   sudo ./install.sh --scheme light  # light Material 3 scheme instead of the default dark one
#   sudo ./install.sh --style list    # rail (default) | clean | list      --no-hints  no key-hint pills      --no-cookie / --no-logo  hide the cookie / only the firmware logo
#   sudo ./install.sh                 # in a terminal, missing choices (resolution, style, scheme, ...) are asked in a TUI; --no-tui or --yes skips it, --tui forces it
#   sudo ./install.sh --prebuilt      # download the release's prebuilt theme (no build tools, no pip; checksum verified)
#   sudo ./install.sh --uninstall
#   Runtime options (STYLE, HINTS, COOKIE, LOGO) go to /etc/material-grub.conf and can be changed later without rebuilding: sudo material-grub-apply
#   options: --no-deps  never touch the package manager     --stage-only  build only, do not touch GRUB
#            --keep-build  keep the temporary build dir     --force  ignore the NixOS check
#            --immutable  use the ostree/bootc layout (automatic when /run/ostree-booted exists)   --yes  do not ask for confirmation
#            --pkg DIR  install a package built elsewhere   --dist-out DIR  with --stage-only: copy the built package to DIR
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
RES=""; SCHEME=dark; SCHEME_SET=0; STYLE=""; COOKIE=""; LOGO=""; HINTS=1; HINTS_SET=0; TUIMODE=auto; IMM=0; YES=0; DL=0; PREBUILT=""; DISTOUT=""; DEPS=1; STAGE=0; KEEP=0; UNINSTALL=0; FORCE=0
while [ $# -gt 0 ]; do
  case $1 in
    --res) RES=${2:?--res needs WxH}; shift;;
    --style) STYLE=${2:?--style needs rail, clean or list}; shift; case $STYLE in rail|clean|list) ;; *) echo "--style must be rail, clean or list" >&2; exit 2;; esac;;
    --cookie) COOKIE=on;; --no-cookie) COOKIE=off;; --logo) LOGO=on;; --no-logo) LOGO=off;; --hints) HINTS=1; HINTS_SET=1;; --tui) TUIMODE=force;; --no-tui) TUIMODE=no;;
    --scheme) SCHEME=${2:?--scheme needs light or dark}; SCHEME_SET=1; shift; case $SCHEME in light|dark) ;; *) echo "--scheme must be light or dark" >&2; exit 2;; esac;;
    --immutable) IMM=1;; --yes|-y) YES=1;; --pkg) PREBUILT=${2:?--pkg needs a directory}; shift;; --dist-out) DISTOUT=${2:?--dist-out needs a directory}; shift;;
    --no-hints) HINTS=0; HINTS_SET=1;; --prebuilt) DL=1;;
    --no-deps) DEPS=0;; --stage-only) STAGE=1;; --keep-build) KEEP=1;; --uninstall) UNINSTALL=1;; --force) FORCE=1;;
    -h|--help) sed -n 2,15p "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2;;
  esac; shift
done

# ---------- output helpers ----------
T0=$(date +%s); TOTAL=6; N=0
if [ -t 1 ]; then TTY=1; B='\033[1m'; D='\033[2m'; M='\033[1;35m'; Y='\033[1;33m'; RD='\033[1;31m'; G='\033[1;32m'; Z='\033[0m'
else TTY=0; B=''; D=''; M=''; Y=''; RD=''; G=''; Z=''; fi
elapsed() { s=$(( $(date +%s) - T0 )); printf '%dm%02ds' $((s / 60)) $((s % 60)); }
step() { N=$((N + 1)); printf "\n${M}[%d/%d]${Z} ${B}%s${Z}  ${D}(total elapsed %s)${Z}\n" "$N" "$TOTAL" "$*" "$(elapsed)"; }
info() { printf '      %s\n' "$*"; }
ok()   { printf "      ${G}ok${Z} %s\n" "$*"; }
warn() { printf "${Y}warning:${Z} %s\n" "$*" >&2; }
die()  { printf "${RD}error:${Z} %s\n" "$*" >&2; exit 1; }

# Wait for a background job, printing a heartbeat so the terminal never looks frozen.
# usage: wait_job PID LOGFILE LABEL [TOTAL_ITEMS]   (items are counted from "scene|bg|theme at" log lines)
wait_job() {
  _pid=$1; _log=$2; _label=$3; _total=${4:-0}; _start=$(date +%s); _last=0
  while kill -0 "$_pid" 2>/dev/null; do
    _now=$(date +%s); _e=$((_now - _start))
    if [ "$_total" -gt 0 ]; then
      _n=$(grep -c -E '^(scene|bg|theme at) ' "$_log" 2>/dev/null || true); _n=${_n:-0}
      _p=$((_n * 100 / _total)); [ "$_p" -gt 99 ] && _p=99
      _msg=$(printf '%s: %d/%d (%d%%)  %dm%02ds elapsed' "$_label" "$_n" "$_total" "$_p" $((_e / 60)) $((_e % 60)))
    else
      _msg=$(printf '%s ... %dm%02ds elapsed' "$_label" $((_e / 60)) $((_e % 60)))
    fi
    if [ "$TTY" = 1 ]; then printf '\r      %s   ' "$_msg"
    elif [ $((_now - _last)) -ge 10 ]; then printf '      %s\n' "$_msg"; _last=$_now; fi
    sleep 2
  done
  [ "$TTY" = 1 ] && printf '\r%*s\r' 78 ''
  if wait "$_pid"; then return 0; else return 1; fi
}

printf "\n${B}Material GRUB installer${Z}\n"

# ---------- [1/6] checks ----------
step "Checking the system"
if [ "$(id -u)" -ne 0 ]; then
  if [ "$STAGE" = 1 ]; then DEPS=0; warn "not running as root: skipping dependency installation (--stage-only)"
  else
    echo "Material GRUB changes system files (/etc/grub.d, /boot) and may install packages."
    echo "Please run the installer with sudo:"
    echo
    echo "    sudo ./install.sh${RES:+ --res $RES}"
    exit 1
  fi
fi
[ "$UNINSTALL" = 1 ] && exec sh "$HERE/install/uninstall.sh"
[ -e /etc/NIXOS ] && [ "$FORCE" = 0 ] && die "NixOS manages GRUB declaratively; this installer does not support it."
[ -e /run/ostree-booted ] && IMM=1
# ---------- questions (TUI) ----------
CONFSETS=""; TUIRAN=0
want_tui() {
  [ "$TUIMODE" != no ] && [ "$YES" = 0 ] && [ -t 0 ] && [ -t 1 ] && command -v python3 >/dev/null 2>&1 || return 1
  [ "$TUIMODE" = force ] && return 0
  [ "$STAGE" = 0 ] && { [ -z "$RES" ] || [ -z "$STYLE" ] || [ "$SCHEME_SET" = 0 ]; }
}
if want_tui; then
  ANS=$(mktemp /var/tmp/material-grub-tui.XXXXXX); PRE=""
  [ -n "$RES" ] && PRE="$PRE --preset RES=$RES"; [ -n "$STYLE" ] && PRE="$PRE --preset STYLE=$STYLE"; [ "$SCHEME_SET" = 1 ] && PRE="$PRE --preset SCHEME=$SCHEME"
  [ -n "$COOKIE" ] && PRE="$PRE --preset COOKIE=$COOKIE"; [ -n "$LOGO" ] && PRE="$PRE --preset LOGO=$LOGO"
  [ "$HINTS_SET" = 1 ] && PRE="$PRE --preset HINTS=$( [ "$HINTS" = 1 ] && echo on || echo off )"
  OFFER=""; [ "$DL" = 0 ] && [ -z "$PREBUILT" ] && OFFER=--prebuilt-ok
  IMMQ=""; [ "$IMM" = 1 ] && [ "$STAGE" = 0 ] && IMMQ=--immutable
  # shellcheck disable=SC2086
  python3 "$HERE/install/tui.py" --out "$ANS" $PRE $OFFER $IMMQ || { rm -f "$ANS"; die "cancelled, nothing was changed"; }
  sed 's/^/A_/' "$ANS" > "$ANS.sh"; . "$ANS.sh"; rm -f "$ANS" "$ANS.sh"
  [ -n "${A_RES:-}" ] && RES=$A_RES; [ -n "${A_STYLE:-}" ] && STYLE=$A_STYLE; [ -n "${A_SCHEME:-}" ] && { SCHEME=$A_SCHEME; SCHEME_SET=1; }
  [ -n "${A_COOKIE:-}" ] && COOKIE=$A_COOKIE; [ -n "${A_LOGO:-}" ] && LOGO=$A_LOGO
  [ -n "${A_HINTS:-}" ] && { [ "$A_HINTS" = off ] && HINTS=0 || HINTS=1; HINTS_SET=1; }
  [ "${A_SOURCE:-}" = prebuilt ] && DL=1; [ "${A_IMMUTABLE:-}" = yes ] && YES=1
  for k in RAW_NAME COUNTDOWN; do eval "v=\${A_$k:-}"; [ -n "$v" ] && [ "$v" = off ] && CONFSETS="$CONFSETS --set $k=off"; done
  [ -n "${A_TIMEOUT:-}" ] && CONFSETS="$CONFSETS --set TIMEOUT=$A_TIMEOUT"
  TUIRAN=1
fi
[ -n "$STYLE" ] && CONFSETS="$CONFSETS --set STYLE=$STYLE"
[ -n "$COOKIE" ] && CONFSETS="$CONFSETS --set COOKIE=$COOKIE"
[ "$COOKIE" = off ] && LOGO=off
[ -n "$LOGO" ] && CONFSETS="$CONFSETS --set LOGO=$LOGO"
[ "$HINTS_SET" = 1 ] && CONFSETS="$CONFSETS --set HINTS=$( [ "$HINTS" = 1 ] && echo on || echo off )"
[ "$SCHEME_SET" = 1 ] && CONFSETS="$CONFSETS --set SCHEME=$SCHEME"
[ -z "$CONFSETS" ] || info "settings for /etc/material-grub.conf:$(echo $CONFSETS | sed 's/--set / /g')"
if [ "$IMM" = 1 ] && [ "$STAGE" = 0 ]; then
  warn "immutable (ostree/bootc) system: using the immutable layout. Support for it is EXPERIMENTAL and could not be tested on a real ostree boot."
  cat <<MSG
      What will be done:
        * nothing is written under /usr; the package and a Python venv go to /var/lib/material-grub, systemd units to /etc/systemd/system
        * the STATIC /boot/grub2/grub.cfg is modified (theme block, Restart/Shut down entries, Advanced-options structure); an untouched copy is kept
          in /var/backups/material-grub, and a raw "All boot entries" submenu is always added as a safety net
        * ostree writes the next deployment's boot entry at shutdown: a unit refreshes our copy afterwards, so the first boot after an update
          may still show the previous list; use the raw submenu if the newest deployment is missing
        * 'bootupctl update' rewrites grub.cfg; a path unit re-applies the theme afterwards
        * build tools (grub-mkfont, rsvg-convert) are never layered with rpm-ostree: the package is built in a throw-away podman container
          (or pass --pkg DIR with a package built on another machine)
      Undo: sudo ./install.sh --uninstall   (restores grub.cfg from the pristine copy)
MSG
  if [ "$YES" = 0 ]; then
    [ -t 0 ] || die "refusing to change the bootloader without confirmation: re-run with --yes"
    printf '      Continue? [y/N] '; read -r ans; case $ans in y|Y|yes|YES) ;; *) die "aborted";; esac
  fi
fi
PM=""
for p in dnf apt-get pacman zypper apk xbps-install; do command -v "$p" >/dev/null 2>&1 && { PM=$p; break; }; done
[ -f /etc/os-release ] && info "distribution: $(. /etc/os-release; echo "${PRETTY_NAME:-$NAME}")  |  package manager: ${PM:-none found}"
info "free space in /var/tmp: $(df -h /var/tmp | awk 'NR==2{print $4}')   (the build needs about 300 MB, removed afterwards)"

# ---------- [2/6] dependencies ----------
step "Checking dependencies"
missing() {   # prints what is missing
  command -v grub2-mkfont >/dev/null 2>&1 || command -v grub-mkfont >/dev/null 2>&1 || printf 'grub-mkfont '
  command -v grub2-mkconfig >/dev/null 2>&1 || command -v grub-mkconfig >/dev/null 2>&1 || printf 'grub-mkconfig '
  command -v rsvg-convert >/dev/null 2>&1 || printf 'rsvg-convert '
  command -v python3 >/dev/null 2>&1 || { printf 'python3 '; return; }
  python3 -c "import venv, ensurepip" 2>/dev/null || printf 'python3-venv '
  python3 -c "import PIL" 2>/dev/null || printf 'python3-pillow '
}
install_deps() {
  case $PM in
    dnf)          dnf install -y grub2-tools grub2-tools-extra librsvg2-tools python3 python3-pip python3-pillow ;;
    apt-get)      apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y grub-common librsvg2-bin python3 python3-venv python3-pip python3-pil ;;
    pacman)       pacman -Syu --needed --noconfirm grub librsvg python python-pip python-pillow ;;
    zypper)       zypper --non-interactive install grub2 rsvg-convert python3 python3-pip python3-Pillow ;;
    apk)          apk add grub grub-mkfont rsvg-convert python3 py3-pip py3-pillow ;;
    xbps-install) xbps-install -Sy grub librsvg-utils python3 python3-pip python3-Pillow ;;
    *) return 1 ;;
  esac
}
VIA_CONTAINER=0
if [ "$IMM" = 1 ]; then
  # immutable: never use the package manager. Only the BUILD tools may be missing (the target machine needs just python3).
  command -v python3 >/dev/null 2>&1 || die "python3 is required"
  if [ -n "$PREBUILT" ] || [ "$DL" = 1 ]; then ok "using a prebuilt package (no build tools needed)"
  else
    MISS=$(missing | sed 's/grub-mkconfig //; s/python3-venv //; s/python3-pillow //')
    if [ -z "$MISS" ]; then ok "build tools found on the host"
    elif command -v podman >/dev/null 2>&1; then info "missing on this immutable host: $MISS"; info "the package will be built in a throw-away podman container"; VIA_CONTAINER=1
    else die "missing build tools: $MISS. Install podman, or build the package elsewhere (./install.sh --stage-only --dist-out DIR) and pass --pkg DIR."; fi
  fi
else
  MISS=$(missing); if [ "$DL" = 1 ] || [ -n "$PREBUILT" ]; then MISS=$(printf %s "$MISS" | sed 's/grub-mkfont //; s/rsvg-convert //; s/python3-venv //'); fi   # a prebuilt package needs no build tools
  if [ -z "$MISS" ]; then ok "everything is already installed (the package manager will not be touched)"
  elif [ "$DEPS" = 0 ]; then die "missing: $MISS (drop --no-deps to let the installer install them)"
  else
    [ -n "$PM" ] || die "missing: $MISS, and no supported package manager was found (dnf, apt, pacman, zypper, apk, xbps)."
    info "missing: $MISS"
    info "installing with $PM (its own output follows; this can take a minute) ..."
    install_deps || die "Dependency installation failed."
    MISS=$(missing); [ -z "$MISS" ] || die "still missing after installation: $MISS"
    ok "dependencies installed"
  fi
fi
GRUB_MKFONT=$(command -v grub2-mkfont || command -v grub-mkfont || true); GRUB_MKCONFIG=$(command -v grub2-mkconfig || command -v grub-mkconfig || true)
[ -f "$HERE/fonts/OFL.txt" ] && ls "$HERE"/fonts/GoogleSansFlex*.ttf >/dev/null 2>&1 || die "fonts/ is incomplete (Google Sans Flex missing)."
ok "tools: ${GRUB_MKFONT:+$(basename "$GRUB_MKFONT"), }${GRUB_MKCONFIG:+$(basename "$GRUB_MKCONFIG"), }python3 $(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"

# ---------- resolution ----------
detect_res() {
  if [ -f /etc/default/grub ]; then
    m=$(sed -n 's/^GRUB_GFXMODE=\([0-9]\{3,5\}x[0-9]\{3,5\}\).*/\1/p' /etc/default/grub | head -n1)
    [ -n "$m" ] && { echo "$m"; return; }
  fi
  best=""; barea=0                      # several monitors: the biggest connected one wins (a small secondary screen must not decide)
  for s in /sys/class/drm/card*-*/status; do
    [ -f "$s" ] && [ "$(cat "$s" 2>/dev/null)" = connected ] || continue
    m=$(head -n1 "$(dirname "$s")/modes" 2>/dev/null); [ -n "$m" ] || continue
    a=$(( ${m%x*} * ${m#*x} )) 2>/dev/null || continue
    [ "$a" -gt "$barea" ] && { barea=$a; best=$m; }
  done
  [ -n "$best" ] && { echo "$best"; return; }
  echo 1920x1080
}
if [ -n "$RES" ]; then info "resolution: $RES ($( [ "$TUIRAN" = 1 ] && echo chosen || echo from --res))"; else RES=$(detect_res); info "resolution: $RES (auto-detected)"; fi
# the bundle to build: the exact resolution if supported, else the closest aspect ratio, then the closest height (same rule as material-grub-assemble)
BUILD_RES=$(python3 -c 'import sys
a="1280x720 1920x1080 1920x1200 2560x1080 2560x1440 2880x1800 3440x1440 3840x1080 3840x1600 3840x2160 5120x1440 5120x2160".split(); w,h=map(int,sys.argv[1].split("x"))
print(sys.argv[1] if sys.argv[1] in a else min(a,key=lambda r:(abs(int(r.split("x")[0])/int(r.split("x")[1])-w/h)>0.02,abs(int(r.split("x")[1])-h))))' "$RES") || die "Bad resolution '$RES' (expected WxH)."
[ "$BUILD_RES" != "$RES" ] && info "$RES is not a built-in size: using the $BUILD_RES theme"
info "supported: 1280x720 1920x1080 1920x1200 2560x1080 2560x1440 2880x1800 3440x1440 3840x1080 3840x1600 3840x2160 5120x1440 5120x2160 (others snap to the closest aspect ratio)"

# ---------- [3/6] build environment ----------
step "Preparing the build environment"
BUILD=$(mktemp -d /var/tmp/material-grub-build.XXXXXX)
cleanup() { [ "$KEEP" = 1 ] && info "build directory kept: $BUILD" || rm -rf "$BUILD"; }
trap cleanup EXIT
info "build directory: $BUILD (your clone stays untouched)"
DIST=$BUILD/dist/material-grub
if [ "$DL" = 1 ] && [ -z "$PREBUILT" ]; then
  VER=$(cat "$HERE/VERSION" 2>/dev/null) || die "VERSION file missing"
  BASE=${MG_RELEASE_URL:-https://github.com/LucaCraft89/material-grub/releases/download/v$VER}
  ASSET=material-grub-$VER-$BUILD_RES-$SCHEME.tar.gz
  fetch() { if command -v curl >/dev/null 2>&1; then curl -fsSL -o "$2" "$1"; elif command -v wget >/dev/null 2>&1; then wget -q -O "$2" "$1"; else return 2; fi; }
  info "downloading $ASSET from $BASE"
  info "(trust: this is code that runs as root. The checksum file comes from the same release, so it protects against corruption, not against a compromised release.)"
  mkdir -p "$BUILD/dl"
  fetch "$BASE/SHA256SUMS" "$BUILD/dl/SHA256SUMS" || die "could not download $BASE/SHA256SUMS (curl or wget needed; is v$VER released?). Build from source by dropping --prebuilt."
  fetch "$BASE/$ASSET" "$BUILD/dl/$ASSET" || die "could not download $ASSET (not every resolution/scheme is published; build from source by dropping --prebuilt)."
  want=$(awk -v f="$ASSET" '$2==f || $2=="*" f {print $1}' "$BUILD/dl/SHA256SUMS")
  [ -n "$want" ] || die "$ASSET is not listed in SHA256SUMS"
  have=$(sha256sum "$BUILD/dl/$ASSET" | awk '{print $1}')
  [ "$want" = "$have" ] || die "checksum mismatch for $ASSET (expected $want, got $have): refusing to install it."
  ok "checksum verified"
  tar -xzf "$BUILD/dl/$ASSET" -C "$BUILD/dl" && PREBUILT=$BUILD/dl/material-grub || die "could not unpack $ASSET"
fi
if [ -n "$PREBUILT" ]; then
  DIST=$PREBUILT; [ -d "$DIST/res" ] && [ -d "$DIST/scenes" ] || die "--pkg $PREBUILT is not a built package (expected res/ and scenes/ inside)."
  ok "skipping the build: using $DIST"
elif [ "$VIA_CONTAINER" = 1 ]; then
  step "Building the package in a throw-away podman container (the host is immutable)"
  mkdir -p "$BUILD/out"; CIMG=${MG_BUILD_IMAGE:-registry.fedoraproject.org/fedora:latest}
  info "image: $CIMG (pulled once; its own output follows). The container installs the build tools and renders the theme."
  podman run --rm --security-opt label=disable -v "$HERE":/src:ro -v "$BUILD/out":/out "$CIMG" \
    sh -c "cd /src && ./install.sh --stage-only --res '$BUILD_RES' --scheme '$SCHEME' --dist-out /out" || die "container build failed (log above)."
  DIST=$BUILD/out/material-grub; [ -d "$DIST/res" ] || die "container build produced no package."
  ok "package built in the container: $DIST"
else
  for d in scripts install vendor fonts; do cp -a "$HERE/$d" "$BUILD/"; done
  cp "$HERE/requirements.txt" "$BUILD/"; cd "$BUILD"
  info "creating a Python virtual environment"
  python3 -m venv --system-site-packages .venv 2>/dev/null || python3 -m venv .venv || die "python3 venv module missing."
  info "installing Python build requirements (fonttools, materialyoucolor); needs network access"
  .venv/bin/pip install --disable-pip-version-check -r requirements.txt >pip.log 2>&1 &
  wait_job $! pip.log "downloading Python packages" 0 || { tail -n 15 pip.log >&2; die "pip failed (network needed)."; }
  ok "build environment ready"

  # ---------- [4/6] render ----------
  step "Rendering the theme (the long step: about 1-3 minutes on a modern CPU, up to 6 on a slow one)"
  info "colour scheme: $SCHEME"
  info "drawing the scene set for $BUILD_RES (native 2160-high design for 4K-class screens), then its theme bundle"
  GSF_FONT=$(ls "$BUILD"/fonts/GoogleSansFlex*.ttf | head -n1); export GSF_FONT PYTHONUNBUFFERED=1
  .venv/bin/python scripts/package.py --res "$BUILD_RES" --scheme "$SCHEME" >build.log 2>&1 &
  PKGPID=$!
  sleep 3; ITEMS=$(sed -n 's/^total \([0-9][0-9]*\)$/\1/p' build.log | head -n1); ITEMS=${ITEMS:-109}
  wait_job "$PKGPID" build.log "rendering scenes" "$ITEMS" || { tail -n 25 build.log >&2; die "Build failed (log above)."; }
  [ -d dist/material-grub ] || die "Build produced no package."
  ok "rendered $(find dist/material-grub/scenes -name '*.png' | wc -l) scene images and $(ls dist/material-grub/res | wc -l) resolution bundles in $(elapsed)"
fi

if [ "$STAGE" = 1 ]; then
  KEEP=1; step "Stage-only: stopping before GRUB is touched"
  if [ -n "$DISTOUT" ]; then mkdir -p "$DISTOUT/material-grub" && cp -a "$DIST/." "$DISTOUT/material-grub/" && ok "package copied to $DISTOUT/material-grub"; fi
  ok "package built at $DIST"; exit 0
fi

# ---------- [5/6] install ----------
step "Installing into GRUB"
sh "$HERE/install/install.sh" --res "$RES" --pkg "$DIST" $( [ "$IMM" = 1 ] && echo --immutable ) $CONFSETS

# ---------- [6/6] done ----------
step "Finished"
printf "      ${G}Material GRUB is installed.${Z} Total time: %s\n\n" "$(elapsed)"
echo "      Reboot to see it. The theme re-applies itself when kernels or boot entries change."
echo "      resolution : $RES            theme : $(ls -d /boot/grub2/themes/material /boot/grub/themes/material 2>/dev/null | head -n1)"
echo "      backups    : /var/backups/material-grub"
echo "      uninstall  : sudo ./install.sh --uninstall"
