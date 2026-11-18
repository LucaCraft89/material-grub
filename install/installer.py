#!/usr/bin/env python3
"""Material GRUB installer (the logic; install.sh is only a POSIX sh bootstrap that finds Python 3.8+ and runs this). stdlib only.

Same flags and steps as the shell installer it replaces: checks, questions (TUI), dependencies, build from source, install into GRUB or
onto a Ventoy stick. The file copying into / is still done by install/install.sh (it also serves `--dest` staging and the packages).
"""

import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # the repository root
sys.path.insert(0, str(HERE / "install"))
sys.path.insert(0, str(HERE / "install/bin"))
import mgrub  # noqa: E402

MIN_RUNTIME = (3, 8)  # this installer and the installed tools
MIN_BUILD = (3, 9)  # the build venv: materialyoucolor has no Python 3.8 wheel
PMS = ("dnf", "apt-get", "pacman", "zypper", "apk", "xbps-install")
# package-manager commands that install the build and runtime dependencies (the same sets as the shell installer)
DEP_COMMANDS = {
    # grub2-tools first, on its own: on RHEL 8 the combined transaction with grub2-tools-extra leaves out grub2-mkconfig
    "dnf": [
        ["dnf", "install", "-y", "grub2-tools"],
        ["dnf", "install", "-y", "grub2-tools-extra", "librsvg2-tools", "python3", "python3-pip", "python3-pillow"],
    ],
    "apt-get": [
        "apt-get",
        "install",
        "-y",
        "grub-common",
        "librsvg2-bin",
        "python3",
        "python3-venv",
        "python3-pip",
        "python3-pil",
    ],
    "pacman": ["pacman", "-Syu", "--needed", "--noconfirm", "grub", "librsvg", "python", "python-pip", "python-pillow"],
    "zypper": [
        "zypper",
        "--non-interactive",
        "install",
        "grub2",
        "rsvg-convert",
        "python3",
        "python3-pip",
        "python3-Pillow",
    ],
    "apk": ["apk", "add", "grub", "grub-mkfont", "rsvg-convert", "python3", "py3-pip", "py3-pillow"],
    "xbps-install": ["xbps-install", "-Sy", "grub", "librsvg-utils", "python3", "python3-pip", "python3-Pillow"],
}
# packages that may provide a newer Python (RHEL 8 ships 3.6 as python3), tried in order
PYTHON_PACKAGES = {
    "dnf": ["python3", "python3.12", "python3.11", "python39", "python3.9"],
    "apt-get": ["python3", "python3.9", "python3.10"],
    "pacman": ["python"],
    "zypper": ["python3", "python311", "python310", "python39"],
    "apk": ["python3"],
    "xbps-install": ["python3"],
}
STYLES = ("rail", "clean", "list", "split", "full")


class LineEvents:
    """File-like stand-in for sys.stdout/sys.stderr in --progress json mode: every printed line becomes a 'log' event."""

    def __init__(self, emit, level):
        self.emit, self.level, self.buf = emit, level, ""

    def write(self, text):
        self.buf += text
        *lines, self.buf = self.buf.split("\n")
        for ln in lines:
            if ln.strip():
                self.emit("log", text=ln.rstrip(), level=self.level)
        return len(text)

    def flush(self):
        if self.buf.strip():
            self.emit("log", text=self.buf.rstrip(), level=self.level)
        self.buf = ""

    def isatty(self):
        return False


class Installer:
    def __init__(self, argv):
        self.argv = argv
        self.t0 = time.time()
        self.total, self.n = 6, 0
        self.tty = sys.stdout.isatty()
        c = self.tty
        self.B, self.D, self.M, self.Y, self.RD, self.G, self.Z = (
            ("\033[1m", "\033[2m", "\033[1;35m", "\033[1;33m", "\033[1;31m", "\033[1;32m", "\033[0m")
            if c
            else ("",) * 7
        )
        # options
        self.ventoy = False
        self.stick = ""
        self.vmode = ""
        self.res = ""
        self.scheme = "dark"
        self.scheme_set = False
        self.style = ""
        self.cookie = ""
        self.logo = ""
        self.hints = True
        self.hints_set = False
        self.tuimode = "auto"
        self.imm = False
        self.yes = False
        self.prebuilt = ""
        self.distout = ""
        self.deps = True
        self.stage = False
        self.dry = False
        self.preview = False
        self.from_package = False
        self.keep = False
        self.uninstall = False
        self.force = False
        self.confsets = []  # (key, value)
        self.tuiran = False
        self.pm = ""
        self.build_dir = None
        self.runtime_py = "python3"
        self.json = False  # --progress json: one JSON object per line on stdout (for the GUI)
        self.out = sys.stdout

    # ------------------------------------------------------------ machine-readable progress
    def emit(self, event, **kw):
        """One line of JSON: {"event": step|info|ok|warn|error|progress|log|done, ...}. Only used with --progress json."""
        if self.json:
            self.out.write(json.dumps({"event": event, "t": round(time.time() - self.t0, 1), **kw}) + "\n")
            self.out.flush()

    def start_json(self):
        self.json, self.yes, self.tuimode, self.tty = True, True, "no", False
        self.B = self.D = self.M = self.Y = self.RD = self.G = self.Z = ""
        sys.stdout, sys.stderr = LineEvents(self.emit, "info"), LineEvents(self.emit, "warn")

    # ------------------------------------------------------------ output helpers
    def elapsed(self):
        s = int(time.time() - self.t0)
        return f"{s // 60}m{s % 60:02d}s"

    def step(self, msg):
        self.n += 1
        if self.json:
            return self.emit("step", n=self.n, total=self.total, msg=msg)
        print(
            f"\n{self.M}[{self.n}/{self.total}]{self.Z} {self.B}{msg}{self.Z}  {self.D}(total elapsed {self.elapsed()}){self.Z}"
        )

    def info(self, msg):
        if self.json:
            return self.emit("info", msg=msg)
        print(f"      {msg}")

    def ok(self, msg):
        if self.json:
            return self.emit("ok", msg=msg)
        print(f"      {self.G}ok{self.Z} {msg}")

    def warn(self, msg):
        if self.json:
            return self.emit("warn", msg=msg)
        print(f"{self.Y}warning:{self.Z} {msg}", file=sys.stderr)

    def die(self, msg, code=1):
        if self.json:
            self.emit("error", msg=msg, code=code)
            sys.exit(code)
        print(f"{self.RD}error:{self.Z} {msg}", file=sys.stderr)
        sys.exit(code)

    def usage_error(self, msg):
        print(msg, file=sys.stderr)
        sys.exit(2)

    # ------------------------------------------------------------ arguments
    def parse(self):
        a = self.argv
        i = 0

        def need(opt, what):
            nonlocal i
            if i + 1 >= len(a):
                print(f"install.sh: {opt} needs {what}", file=sys.stderr)
                sys.exit(1)
            i += 1
            return a[i]

        while i < len(a):
            o = a[i]
            if o == "--res":
                self.res = need(o, "WxH")
            elif o == "--ventoy":
                self.ventoy = True
                if i + 1 < len(a) and a[i + 1] and not a[i + 1].startswith("-"):
                    i += 1
                    self.stick = a[i]
            elif o == "--mode":
                self.vmode = need(o, "dynamic or snapshot")
                if self.vmode not in ("dynamic", "snapshot"):
                    self.usage_error("--mode must be dynamic or snapshot")
            elif o == "--style":
                self.style = need(o, "rail, clean, list, split or full")
                if self.style not in STYLES:
                    self.usage_error("--style must be rail, clean, list, split or full (full and list are for Ventoy)")
            elif o == "--cookie":
                self.cookie = "on"
            elif o == "--no-cookie":
                self.cookie = "off"
            elif o == "--logo":
                self.logo = "on"
            elif o == "--no-logo":
                self.logo = "off"
            elif o == "--hints":
                self.hints, self.hints_set = True, True
            elif o == "--no-hints":
                self.hints, self.hints_set = False, True
            elif o == "--tui":
                self.tuimode = "force"
            elif o == "--no-tui":
                self.tuimode = "no"
            elif o == "--scheme":
                self.scheme = need(o, "light or dark")
                self.scheme_set = True
                if self.scheme not in ("light", "dark"):
                    self.usage_error("--scheme must be light or dark")
            elif o == "--immutable":
                self.imm = True
            elif o in ("--yes", "-y"):
                self.yes = True
            elif o == "--pkg":
                self.prebuilt = need(o, "a directory")
            elif o == "--dist-out":
                self.distout = need(o, "a directory")
            elif o == "--no-deps":
                self.deps = False
            elif o == "--stage-only":
                self.stage = True
            elif o == "--dry-run":
                self.dry, self.deps = True, False
            elif (
                o == "--from-package"
            ):  # run by a distribution package (postinst, %posttrans, pacman hook): never asks, never fails the transaction
                self.from_package, self.yes, self.deps, self.tuimode = True, True, False, "no"
            elif o == "--preview":
                self.preview, self.deps = True, False
            elif o == "--progress":
                if need(o, "json") != "json":
                    self.usage_error("--progress only knows json")
                self.json = True
            elif o == "--keep-build":
                self.keep = True
            elif o == "--uninstall":
                self.uninstall = True
            elif o == "--force":
                self.force = True
            elif o in ("-h", "--help"):
                self.help()
            else:
                self.usage_error(f"unknown option: {o} (try --help)")
            i += 1

    def help(self):
        lines = (HERE / "install.sh").read_text().splitlines()
        end = next(i for i, l in enumerate(lines) if not l.startswith("#") or l.startswith("#   The logic is"))
        for l in lines[1:end]:
            print(re.sub(r"^# ?", "", l))
        sys.exit(0)

    # ------------------------------------------------------------ small helpers
    def root(self):
        return os.geteuid() == 0

    def run(self, cmd, **kw):
        cmd = [str(c) for c in cmd]
        if not self.json or "capture_output" in kw or "stdout" in kw:
            return subprocess.run(cmd, **kw)
        # json mode: the child's output becomes 'log' events instead of leaking onto our stdout
        p = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", **kw
        )
        with p.stdout:
            for line in p.stdout:
                if line.strip():
                    self.emit("log", text=line.rstrip(), level="info")
        return subprocess.CompletedProcess(cmd, p.wait())

    def have(self, name):
        return shutil.which(name) is not None

    def wait_job(self, proc, log, label, total=0):
        """Wait for a background process, printing a heartbeat so the terminal never looks frozen."""
        start, last, seen = time.time(), 0.0, 0
        while proc.poll() is None:
            now = time.time()
            e = int(now - start)
            if total > 0:
                try:
                    count = sum(
                        1
                        for l in Path(log).read_text(errors="ignore").splitlines()
                        if re.match(r"^(scene|bg|theme at) ", l)
                    )
                except OSError:
                    count = 0
                p = min(count * 100 // total, 99)
                msg = f"{label}: {count}/{total} ({p}%)  {e // 60}m{e % 60:02d}s elapsed"
            else:
                msg = f"{label} ... {e // 60}m{e % 60:02d}s elapsed"
            if self.json:
                if now - last >= 2:
                    self.emit(
                        "progress",
                        label=label,
                        count=count if total > 0 else None,
                        total=total or None,
                        percent=p if total > 0 else None,
                        elapsed=e,
                    )
                    last = now
                try:  # the job's own log lines, for the verbose view
                    lines = Path(log).read_text(errors="ignore").splitlines()
                except OSError:
                    lines = []
                for ln in lines[seen:]:
                    self.emit("log", text=ln, level="info")
                seen = len(lines)
            elif self.tty:
                sys.stdout.write(f"\r      {msg}   ")
                sys.stdout.flush()
            elif now - last >= 10:
                print(f"      {msg}", flush=True)
                last = now
            time.sleep(2)
        if self.tty:
            sys.stdout.write("\r" + " " * 78 + "\r")
        return proc.returncode == 0

    @staticmethod
    def py_version(py):
        try:
            r = subprocess.run(
                [py, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"], capture_output=True, text=True
            )
            return tuple(int(x) for x in r.stdout.strip().split(".")) if r.returncode == 0 else None
        except OSError:
            return None

    def py_has(self, py, module):
        return subprocess.run([py, "-c", f"import {module}"], capture_output=True).returncode == 0

    # ------------------------------------------------------------ steps
    def check_system(self):
        print(f"\n{self.B}Material GRUB installer{self.Z}")
        self.step("Checking the system")
        if self.ventoy and not self.root():
            self.deps = False
            self.info(
                "not running as root: fine for a Ventoy stick (dependencies must already be installed; use sudo to let the installer install them)"
            )
        elif not self.root():
            if self.stage or self.dry or self.preview:
                self.deps = False
                self.warn("not running as root: skipping dependency installation (--stage-only / --dry-run)")
            else:
                print("Material GRUB changes system files (/etc/grub.d, /boot) and may install packages.")
                print("Please run the installer with sudo:")
                print()
                print(f"    sudo ./install.sh{(' --res ' + self.res) if self.res else ''}")
                sys.exit(1)
        if self.uninstall and self.ventoy:
            if not self.stick:
                self.stick = self.only_mounted_stick()
                if not self.stick:
                    self.die(
                        "give the mount point of the stick: ./install.sh --uninstall --ventoy /run/media/you/Ventoy"
                    )
            sys.exit(
                self.run(
                    [sys.executable, HERE / "install/bin/material-grub-ventoy", self.stick, "--uninstall"]
                ).returncode
            )
        if self.uninstall:
            sys.exit(self.run(["sh", HERE / "install/uninstall.sh"]).returncode)
        if not self.ventoy:
            if Path("/etc/NIXOS").exists() and not self.force:
                self.die("NixOS manages GRUB declaratively; this installer does not support it.")
            if Path("/run/ostree-booted").exists():
                self.imm = True

    def only_mounted_stick(self):
        r = self.run([sys.executable, HERE / "install/ventoy_sticks.py", "--json"], capture_output=True, text=True)
        try:
            mounted = [s["path"] for s in json.loads(r.stdout) if s["mounted"]]
        except ValueError:
            mounted = []
        return mounted[0] if len(mounted) == 1 else ""

    def want_tui(self):
        if self.tuimode == "no" or self.yes or not (sys.stdin.isatty() and sys.stdout.isatty()):
            return False
        if self.tuimode == "force":
            return True
        if self.ventoy and (not self.stick or not self.res or not self.style or not self.scheme_set):
            return True
        return not self.stage and not self.preview and (not self.res or not self.style or not self.scheme_set)

    def questions(self):
        if self.want_tui():
            fd, ans = tempfile.mkstemp(
                prefix="material-grub-tui.", dir="/var/tmp" if os.path.isdir("/var/tmp") else None
            )
            os.close(fd)
            pre = []

            def preset(k, v):
                pre.extend(["--preset", f"{k}={v}"])

            if self.res:
                preset("RES", self.res)
            if self.style:
                preset("STYLE", self.style)
            if self.scheme_set:
                preset("SCHEME", self.scheme)
            if self.cookie:
                preset("COOKIE", self.cookie)
            if self.logo:
                preset("LOGO", self.logo)
            if self.hints_set:
                preset("HINTS", "on" if self.hints else "off")
            if self.ventoy:
                preset("TARGET", "ventoy")
            if self.stick:
                preset("STICK", self.stick)
            if self.vmode:
                preset("MODE", self.vmode)
            if not self.ventoy and not self.imm and not self.stage:
                pre.append("--ask-target")
            if self.imm and not self.stage:
                pre.append("--immutable")
            r = self.run([sys.executable, HERE / "install/tui.py", "--out", ans, *pre])
            if r.returncode != 0:
                Path(ans).unlink(missing_ok=True)
                self.die("cancelled, nothing was changed")
            a = self.read_answers(ans)
            Path(ans).unlink(missing_ok=True)
            self.apply_answers(a)
        self.build_settings()

    @staticmethod
    def read_answers(path):
        out = {}
        for line in Path(path).read_text().splitlines():
            k, sep, v = line.partition("=")
            if sep:
                out[k.strip()] = (shlex.split(v) or [""])[0]
        return out

    def apply_answers(self, a):
        if a.get("RES"):
            self.res = a["RES"]
        if a.get("STYLE"):
            self.style = a["STYLE"]
        if a.get("SCHEME"):
            self.scheme, self.scheme_set = a["SCHEME"], True
        if a.get("COOKIE"):
            self.cookie = a["COOKIE"]
        if a.get("LOGO"):
            self.logo = a["LOGO"]
        if a.get("HINTS"):
            self.hints, self.hints_set = a["HINTS"] != "off", True
        if a.get("IMMUTABLE") == "yes":
            self.yes = True
        if a.get("TARGET") == "ventoy":
            self.ventoy = True
        if a.get("STICK"):
            self.stick = a["STICK"]
        if a.get("MODE"):
            self.vmode = a["MODE"]
        if a.get("RESX"):
            self.res = f"{self.res},{a['RESX']}"
        for k in ("RAW_NAME", "COUNTDOWN"):
            if a.get(k) == "off":
                self.confsets.append((k, "off"))
        if a.get("TIMEOUT"):
            self.confsets.append(("TIMEOUT", a["TIMEOUT"]))
        self.tuiran = True

    def build_settings(self):
        c = self.confsets
        if self.style:
            c.append(("STYLE", self.style))
        if self.cookie:
            c.append(("COOKIE", self.cookie))
        if self.cookie == "off":
            self.logo = "off"
        if self.logo:
            c.append(("LOGO", self.logo))
        if self.hints_set:
            c.append(("HINTS", "on" if self.hints else "off"))
        if self.scheme_set:
            c.append(("SCHEME", self.scheme))
        if self.ventoy:
            c.append(("MODE", self.vmode or "dynamic"))
            self.total = 5
            if not self.stick:
                self.die(
                    "no Ventoy stick given: ./install.sh --ventoy /run/media/you/Ventoy   (or run it in a terminal to pick one)"
                )
            if not self.stick.startswith("dev:"):
                r = self.run(
                    [sys.executable, HERE / "install/ventoy_sticks.py", "--check", self.stick], capture_output=True
                )
                if r.returncode != 0:
                    self.die(
                        f"{self.stick} is not the data partition of a Ventoy stick (its disk has no VTOYEFI partition and it has no /ventoy folder). "
                        "Use the big partition of a stick prepared with Ventoy."
                    )
        if c:
            where = "the Ventoy stick" if self.ventoy else "/etc/material-grub.conf"
            self.info(f"settings for {where}: " + " ".join(f"{k}={v}" for k, v in c))

    def confset_args(self):
        out = []
        for k, v in self.confsets:
            out += ["--set", f"{k}={v}"]
        return out

    def immutable_notice(self):
        if not (self.imm and not self.stage):
            return
        self.warn(
            "immutable (ostree/bootc) system: using the immutable layout. Support for it is EXPERIMENTAL and could not be tested on a real ostree boot."
        )
        print("""      What will be done:
        * nothing is written under /usr; the package and a Python venv go to /var/lib/material-grub, systemd units to /etc/systemd/system
        * the STATIC /boot/grub2/grub.cfg is modified (theme block, Restart/Shut down entries, Advanced-options structure); an untouched copy is kept
          in /var/backups/material-grub, and a raw "All boot entries" submenu is always added as a safety net
        * ostree writes the next deployment's boot entry at shutdown: a unit refreshes our copy afterwards, so the first boot after an update
          may still show the previous list; use the raw submenu if the newest deployment is missing
        * 'bootupctl update' rewrites grub.cfg; a path unit re-applies the theme afterwards
        * build tools (grub-mkfont, rsvg-convert) are never layered with rpm-ostree: the package is built in a throw-away podman container
          (or pass --pkg DIR with a package built on another machine)
      Undo: sudo ./install.sh --uninstall   (restores grub.cfg from the pristine copy)""")
        if not self.yes:
            if not sys.stdin.isatty():
                self.die("refusing to change the bootloader without confirmation: re-run with --yes")
            ans = input("      Continue? [y/N] ")
            if ans not in ("y", "Y", "yes", "YES"):
                self.die("aborted")

    def environment_info(self):
        for p in PMS:
            if self.have(p):
                self.pm = p
                break
        osr = {}
        try:
            for l in Path("/etc/os-release").read_text().splitlines():
                k, _, v = l.partition("=")
                osr[k] = v.strip('"')
            self.info(
                f"distribution: {osr.get('PRETTY_NAME') or osr.get('NAME', '')}  |  package manager: {self.pm or 'none found'}"
            )
        except OSError:
            pass
        free = self.run(["df", "-h", "/var/tmp"], capture_output=True, text=True).stdout.splitlines()
        if len(free) > 1:
            self.info(
                f"free space in /var/tmp: {free[1].split()[3]}   (the build needs about 300 MB, removed afterwards)"
            )

    # ------------------------------------------------------------ dependencies
    def missing(self, build_py=None):
        """What is missing, with the same names the shell installer printed."""
        out = []
        if not (self.have("grub2-mkfont") or self.have("grub-mkfont")):
            out.append("grub-mkfont")
        if not self.ventoy and not (self.have("grub2-mkconfig") or self.have("grub-mkconfig")):
            out.append("grub-mkconfig")
        if not self.have("rsvg-convert"):
            out.append("rsvg-convert")
        py = build_py or sys.executable
        if not (self.py_has(py, "venv") and self.py_has(py, "ensurepip")):
            out.append("python3-venv")
        p3 = shutil.which("python3")
        system_py = bool(p3) and os.path.realpath(p3) == os.path.realpath(py)
        if system_py and not self.py_has(
            py, "PIL"
        ):  # another interpreter (RHEL 8's python3.12) gets Pillow in a venv at install time
            out.append("python3-pillow")
        return out

    def dependencies(self):
        self.step("Checking dependencies")
        self.via_container = False
        if self.imm:
            # immutable: never use the package manager. Only the BUILD tools may be missing (the target machine needs just python3).
            if self.prebuilt:
                self.ok("using a package built elsewhere (--pkg): no build tools needed")
            else:
                miss = [m for m in self.missing() if m not in ("grub-mkconfig", "python3-venv", "python3-pillow")]
                if not miss:
                    self.ok("build tools found on the host")
                elif self.have("podman"):
                    self.info(f"missing on this immutable host: {' '.join(miss)}")
                    self.info("the package will be built in a throw-away podman container")
                    self.via_container = True
                else:
                    self.die(
                        f"missing build tools: {' '.join(miss)}. Install podman, or build the package elsewhere "
                        "(./install.sh --stage-only --dist-out DIR) and pass --pkg DIR."
                    )
        else:
            miss = self.missing()
            if self.prebuilt:  # a prebuilt package needs no build tools
                miss = [m for m in miss if m not in ("grub-mkfont", "rsvg-convert", "python3-venv")]
            if not miss:
                self.ok("everything is already installed (the package manager will not be touched)")
            elif not self.deps:
                self.die(f"missing: {' '.join(miss)} (drop --no-deps to let the installer install them)")
            else:
                if not self.pm:
                    self.die(
                        f"missing: {' '.join(miss)}, and no supported package manager was found (dnf, apt, pacman, zypper, apk, xbps)."
                    )
                self.info(f"missing: {' '.join(miss)}")
                self.info(f"installing with {self.pm} (its own output follows; this can take a minute) ...")
                self.install_deps()
                miss = self.missing()
                if miss:
                    self.die(f"still missing after installation: {' '.join(miss)}")
                self.ok("dependencies installed")
        mkfont = shutil.which("grub2-mkfont") or shutil.which("grub-mkfont")
        mkconfig = shutil.which("grub2-mkconfig") or shutil.which("grub-mkconfig")
        if not (HERE / "fonts/OFL.txt").is_file() or not glob.glob(str(HERE / "fonts/GoogleSansFlex*.ttf")):
            self.die("fonts/ is incomplete (Google Sans Flex missing).")
        tools = [os.path.basename(t) for t in (mkfont, mkconfig) if t]
        v = sys.version_info
        self.ok("tools: " + ", ".join(tools + [f"python3 {v[0]}.{v[1]}"]))

    def install_deps(self):
        env = dict(os.environ)
        if self.pm == "apt-get":
            if self.run(["apt-get", "update"]).returncode != 0:
                self.die("Dependency installation failed.")
            env["DEBIAN_FRONTEND"] = "noninteractive"
        cmds = DEP_COMMANDS[self.pm]
        for cmd in cmds if isinstance(cmds[0], list) else [cmds]:
            if self.run(cmd, env=env).returncode != 0:
                self.die("Dependency installation failed.")

    def build_python(self):
        """A Python 3.9+ with venv for the build; installs one with the package manager when only an older one exists."""
        names = ["python3"] + [f"python3.{m}" for m in range(14, 8, -1)]

        def find():
            for n in names:
                p = shutil.which(n)
                v = self.py_version(p) if p else None
                if v and v >= MIN_BUILD and self.py_has(p, "venv"):
                    return p
            return None

        p = find()
        if p:
            return p
        if self.deps and self.root() and self.pm in PYTHON_PACKAGES:
            self.info(f"the build needs Python {MIN_BUILD[0]}.{MIN_BUILD[1]} or newer; installing one with {self.pm}")
            for pkg in PYTHON_PACKAGES[self.pm]:
                cmd = {
                    "dnf": ["dnf", "install", "-y"],
                    "apt-get": ["apt-get", "install", "-y"],
                    "pacman": ["pacman", "-Syu", "--needed", "--noconfirm"],
                }.get(self.pm, [self.pm, "install", "-y"] if self.pm != "apk" else ["apk", "add"])
                if self.pm == "zypper":
                    cmd = ["zypper", "--non-interactive", "install"]
                if self.pm == "xbps-install":
                    cmd = ["xbps-install", "-Sy"]
                self.run(cmd + [pkg], capture_output=True)
                p = find()
                if p:
                    return p
        self.die(
            f"the build needs Python {MIN_BUILD[0]}.{MIN_BUILD[1]} or newer with venv (found {sys.version_info[0]}.{sys.version_info[1]}). "
            "Install one (RHEL 8 family: dnf install python39) or build the package elsewhere (./install.sh --stage-only --dist-out DIR) and pass --pkg DIR."
        )

    # ------------------------------------------------------------ resolution
    def detect_res(self):
        try:
            for l in Path("/etc/default/grub").read_text().splitlines():
                m = re.match(r"^GRUB_GFXMODE=([0-9]{3,5}x[0-9]{3,5})", l)
                if m:
                    return m.group(1)
        except OSError:
            pass
        best, barea = (
            "",
            0,
        )  # several monitors: the biggest connected one wins (a small secondary screen must not decide)
        for s in sorted(glob.glob("/sys/class/drm/card*-*/status")):
            try:
                if Path(s).read_text().strip() != "connected":
                    continue
                m = Path(s).with_name("modes").read_text().splitlines()[0]
                w, h = m.split("x")
                area = int(w) * int(h)
            except (OSError, ValueError, IndexError):
                continue
            if area > barea:
                barea, best = area, m
        return best or "1920x1080"

    def resolution(self):
        if self.res:
            self.info(f"resolution: {self.res} ({'chosen' if self.tuiran else 'from --res'})")
        else:
            self.res = self.detect_res()
            self.info(f"resolution: {self.res} (auto-detected)")
        if not self.ventoy and "," in self.res:
            self.die("several resolutions (--res A,B) are only supported with --ventoy")
        out = []
        for r in self.res.split(","):
            try:
                s = mgrub.snap(r)
            except ValueError:
                self.die(f"Bad resolution '{self.res}' (expected WxH).")
            if s not in out:
                out.append(s)
        self.build_res = ",".join(out)
        if self.build_res != self.res:
            self.info(f"{self.res} is not a built-in size: using the {self.build_res} theme")
        self.info(f"supported: {' '.join(mgrub.RESOLUTIONS)} (others snap to the closest aspect ratio)")

    # ------------------------------------------------------------ build
    def build(self):
        self.step("Preparing the build environment")
        self.build_dir = Path(
            tempfile.mkdtemp(prefix="material-grub-build.", dir="/var/tmp" if os.path.isdir("/var/tmp") else None)
        )
        self.info(f"build directory: {self.build_dir} (your clone stays untouched)")
        self.dist = self.build_dir / "dist/material-grub"
        if self.prebuilt:
            self.dist = Path(self.prebuilt)
            if not ((self.dist / "res").is_dir() and (self.dist / "scenes").is_dir()):
                self.die(f"--pkg {self.prebuilt} is not a built package (expected res/ and scenes/ inside).")
            self.ok(f"skipping the build: using {self.dist}")
        elif self.via_container:
            self.build_in_container()
        else:
            self.build_here()

    def build_in_container(self):
        self.step("Building the package in a throw-away podman container (the host is immutable)")
        out = self.build_dir / "out"
        out.mkdir()
        img = os.environ.get("MG_BUILD_IMAGE", "registry.fedoraproject.org/fedora:latest")
        self.info(
            f"image: {img} (pulled once; its own output follows). The container installs the build tools and renders the theme."
        )
        inner = (
            f"cd /src && ./install.sh --stage-only --res '{self.build_res}' --scheme '{self.scheme}' --dist-out /out"
        )
        r = self.run(
            [
                "podman",
                "run",
                "--rm",
                "--security-opt",
                "label=disable",
                "-v",
                f"{HERE}:/src:ro",
                "-v",
                f"{out}:/out",
                img,
                "sh",
                "-c",
                inner,
            ]
        )
        if r.returncode != 0:
            self.die("container build failed (log above).")
        self.dist = out / "material-grub"
        if not (self.dist / "res").is_dir():
            self.die("container build produced no package.")
        self.ok(f"package built in the container: {self.dist}")

    def build_here(self):
        b = self.build_dir
        for d in ("scripts", "install", "vendor", "fonts"):
            shutil.copytree(HERE / d, b / d, symlinks=True)
        for f in ("requirements.txt", "VERSION"):
            shutil.copy(HERE / f, b / f)
        py = self.build_python()
        self.info("creating a Python virtual environment")
        r = self.run([py, "-m", "venv", "--system-site-packages", ".venv"], cwd=b, capture_output=True)
        if r.returncode != 0:
            r = self.run([py, "-m", "venv", ".venv"], cwd=b, capture_output=True)
            if r.returncode != 0:
                self.die("python3 venv module missing.")
        self.info("installing Python build requirements (fonttools, materialyoucolor); needs network access")
        with open(b / "pip.log", "w") as log:
            p = subprocess.Popen(
                [
                    str(b / ".venv/bin/pip"),
                    "install",
                    "--disable-pip-version-check",
                    "--require-hashes",
                    "-r",
                    "requirements.txt",
                ],
                cwd=b,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            good = self.wait_job(p, b / "pip.log", "downloading Python packages")
        if not good:
            print("\n".join((b / "pip.log").read_text().splitlines()[-15:]), file=sys.stderr)
            self.die("pip failed (network needed).")
        self.ok("build environment ready")

        self.step("Rendering the theme (the long step: about 1-3 minutes on a modern CPU, up to 6 on a slow one)")
        self.info(f"colour scheme: {self.scheme}")
        self.info(
            f"drawing the scene set for {self.build_res} (native 2160-high design for 4K-class screens), then its theme bundle"
        )
        env = dict(
            os.environ, PYTHONUNBUFFERED="1", GSF_FONT=sorted(glob.glob(str(b / "fonts/GoogleSansFlex*.ttf")))[0]
        )
        with open(b / "build.log", "w") as log:
            p = subprocess.Popen(
                [str(b / ".venv/bin/python"), "scripts/package.py", "--res", self.build_res, "--scheme", self.scheme],
                cwd=b,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=env,
            )
            time.sleep(3)
            m = re.search(r"^total ([0-9]+)$", (b / "build.log").read_text(errors="ignore"), re.M)
            items = int(m.group(1)) if m else 109
            good = self.wait_job(p, b / "build.log", "rendering scenes", items)
        if not good:
            print("\n".join((b / "build.log").read_text().splitlines()[-25:]), file=sys.stderr)
            self.die("Build failed (log above).")
        if not (b / "dist/material-grub").is_dir():
            self.die("Build produced no package.")
        scenes = sum(1 for _ in (b / "dist/material-grub/scenes").rglob("*.png"))
        bundles = len(list((b / "dist/material-grub/res").iterdir()))
        self.ok(f"rendered {scenes} scene images and {bundles} resolution bundles in {self.elapsed()}")

    # ------------------------------------------------------------ install
    def prepare_runtime_python(self):
        """The interpreter the installed hooks will use: python3 when it is 3.8+ with Pillow, else this one, else a venv with Pillow."""
        p3 = shutil.which("python3")
        v = self.py_version(p3) if p3 else None
        if v and v >= MIN_RUNTIME and self.py_has(p3, "PIL"):
            self.runtime_py = "python3"
            return
        if self.py_has(sys.executable, "PIL"):
            self.runtime_py = sys.executable
            return
        venv = Path("/var/lib/material-grub/venv")
        self.info(
            f"Pillow is not available for Python {sys.version_info[0]}.{sys.version_info[1]}: creating a venv in {venv} (pip, needs network)"
        )
        venv.parent.mkdir(parents=True, exist_ok=True)
        if self.run([sys.executable, "-m", "venv", venv]).returncode != 0:
            self.die("could not create the Pillow venv")
        r = self.run(
            [
                venv / "bin/pip",
                "install",
                "--disable-pip-version-check",
                "--require-hashes",
                "-r",
                HERE / "requirements.txt",
            ],
            capture_output=True,
        )
        if r.returncode != 0:
            self.die("could not install Pillow into the venv (network needed)")
        self.runtime_py = str(venv / "bin/python3")

    def ventoy_install(self):
        self.step("Installing onto the Ventoy stick")
        if not self.stick:
            self.die("no Ventoy stick given: ./install.sh --ventoy /run/media/you/Ventoy")
        mounted_by_us, udisks_dev = "", ""
        stick = self.stick
        try:
            if stick.startswith("dev:"):  # not mounted: mount it for the copy, unmount at the end
                dev = stick[4:]
                mnt = tempfile.mkdtemp(prefix="material-grub-stick.", dir="/var/tmp")
                if self.root():
                    if self.run(["mount", dev, mnt]).returncode != 0:
                        self.die(f"could not mount {dev}")
                    mounted_by_us = mnt
                else:
                    os.rmdir(mnt)
                    r = self.run(["udisksctl", "mount", "-b", dev], capture_output=True, text=True)
                    out = (r.stdout + r.stderr).strip()
                    if r.returncode != 0:
                        self.die(f"could not mount {dev} (mount it in your file manager, or run with sudo): {out}")
                    m = re.search(r" at (.*)\.$", out)
                    mnt = m.group(1) if m else ""
                    if not os.path.isdir(mnt):
                        self.die(f"mounted {dev} but could not find where: {out}")
                    udisks_dev = dev
                stick = mnt
                self.info(f"mounted {dev} at {stick}")
            r = self.run([sys.executable, HERE / "install/ventoy_sticks.py", "--check", stick], capture_output=True)
            if r.returncode != 0:
                self.die(
                    f"{stick} is not the data partition of a Ventoy stick (its disk has no VTOYEFI partition and it has no /ventoy folder)."
                )
            vdir = Path(stick) / "ventoy"
            if not vdir.is_dir():
                vdir.mkdir(parents=True)
                self.info(f"created {vdir} (a fresh Ventoy stick has none)")
            conf = vdir / "material-grub.conf"
            conf.write_text("".join(f"{k}={v}\n" for k, v in self.confsets))
            self.info(f"options written to {conf}: " + " ".join(f"{k}={v}" for k, v in self.confsets) + " ")
            r = self.run(
                [
                    sys.executable,
                    HERE / "install/bin/material-grub-ventoy",
                    stick,
                    "--pkg",
                    self.dist,
                    "--res",
                    self.build_res,
                ]
            )
            if r.returncode != 0:
                self.die("the Ventoy installation failed (output above).")
            self.run(["sync"])
            if mounted_by_us:
                if self.run(["umount", mounted_by_us]).returncode == 0:
                    os.rmdir(mounted_by_us)
                    mounted_by_us = ""
                    self.info("stick unmounted: safe to remove")
            if udisks_dev and self.run(["udisksctl", "unmount", "-b", udisks_dev], capture_output=True).returncode == 0:
                self.info("stick unmounted: safe to remove")
        finally:
            pass
        self.step("Finished")
        print(f"      {self.G}The Ventoy stick is themed.{self.Z} Total time: {self.elapsed()}\n")
        print(
            "      Boot from it. In the default (dynamic) mode you can add, remove or rename ISOs on any computer: the theme follows, nothing to re-run."
        )
        print(
            "      Change the style, scheme or resolutions: run this installer again.   Undo: ./install.sh --uninstall --ventoy MOUNTPOINT"
        )

    def grub_install(self):
        step_cmd = ["sh", HERE / "install/install.sh", "--res", self.res, "--pkg", self.dist]
        if self.imm:
            step_cmd.append("--immutable")
        self.step("Installing into GRUB")
        if not self.imm:
            self.prepare_runtime_python()
        if self.runtime_py != "python3":
            step_cmd += ["--py", self.runtime_py]
        r = self.run(step_cmd + self.confset_args())
        if r.returncode != 0:
            sys.exit(r.returncode)
        self.step("Finished")
        print(f"      {self.G}Material GRUB is installed.{self.Z} Total time: {self.elapsed()}\n")
        print("      Reboot to see it. The theme re-applies itself when kernels or boot entries change.")
        theme = next((p for p in ("/boot/grub2/themes/material", "/boot/grub/themes/material") if os.path.isdir(p)), "")
        print(f"      resolution : {self.res}            theme : {theme}")
        print("      backups    : /var/backups/material-grub")
        print("      uninstall  : sudo ./install.sh --uninstall")

    # ------------------------------------------------------------ main
    def main(self):
        self.parse()
        if self.json:
            self.start_json()
            try:
                rc = self.main_inner()
            except SystemExit as e:
                rc = e.code if isinstance(e.code, int) else 1
            sys.stdout.flush()
            sys.stderr.flush()
            self.emit("done", rc=rc or 0, ok=not rc, elapsed=self.elapsed())
            return rc or 0
        return self.main_inner()

    def main_inner(self):
        if not self.from_package:
            return self.run_all()
        # packages: keep the user's scheme, pick the resolution like a plain run; a failure must not break the package transaction
        conf = mgrub.load_conf()
        if not self.scheme_set and Path("/etc/material-grub.conf").is_file():
            self.scheme = conf["SCHEME"]
        try:
            rc = self.run_all()
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 1
        if rc not in (0, None):
            import mgsafe

            reason = "the Material GRUB package could not finish its install or update"
            mgsafe.report_failure(
                reason,
                [f"the installer exited with status {rc} (output above)", "your GRUB menu was left working as before"],
            )
        return 0

    def run_all(self):
        self.check_system()
        self.questions()
        self.immutable_notice()
        self.environment_info()
        self.dependencies()
        self.resolution()
        try:
            self.build()
            if self.dry:
                if self.ventoy:
                    self.die(
                        "--dry-run shows a PC install; for a Ventoy stick use --stage-only and look at the stick afterwards."
                    )
                self.step("Dry run: building a scratch install (nothing is written to the system)")
                cmd = [
                    sys.executable,
                    HERE / "install/bin/material-grub-dryrun",
                    "--pkg",
                    self.dist,
                    "--res",
                    self.build_res,
                    "--installer",
                    HERE / "install",
                ]
                if self.imm:
                    cmd.append("--immutable")
                return self.run(cmd + self.confset_args()).returncode
            if self.preview:
                self.step("Preview: rendering your menu (nothing is installed)")
                cmd = [
                    sys.executable,
                    HERE / "install/bin/material-grub-preview",
                    "--pkg",
                    self.dist,
                    "--res",
                    self.build_res,
                ]
                if self.style:
                    cmd += ["--style", self.style]
                return self.run(cmd).returncode
            if self.stage:
                self.keep = True
                self.step("Stage-only: stopping before GRUB is touched")
                if self.distout:
                    out = Path(self.distout) / "material-grub"
                    out.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(self.dist, out, dirs_exist_ok=True, symlinks=True)
                    self.ok(f"package copied to {out}")
                self.ok(f"package built at {self.dist}")
                return 0
            if self.ventoy:
                self.ventoy_install()
                return 0
            self.grub_install()
            return 0
        finally:
            if self.build_dir:
                if self.keep:
                    self.info(f"build directory kept: {self.build_dir}")
                else:
                    shutil.rmtree(self.build_dir, ignore_errors=True)


def main(argv=None):
    try:
        return Installer(list(sys.argv[1:] if argv is None else argv)).main()
    except KeyboardInterrupt:
        print("\ninterrupted, nothing more was changed", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
