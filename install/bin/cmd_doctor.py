"""material-grub doctor: check the installation and print a report that can be pasted into a bug report. stdlib only.

usage: material-grub doctor [--root DIR] [--json | --status-json]       (also: material-grub apply --status)
Exit status: 0 when nothing failed (warnings are fine), 1 when something failed.
--json: the list of checks. --status-json: one object for the GUI (installed, version, style, scheme, health, checks).
--root DIR looks at an installation staged under DIR (tests, `install.sh --dest`); systemd is not asked then.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import mgoverrides
import mgrub
import mgsafe
import mgtheme

OK, WARN, FAIL, INFO = "ok", "warn", "FAIL", "info"
MARK = "# material-grub: classes applied"
HOOKS = ("05_material", "15_material_menu", "90_material_system")


class Doctor:
    def __init__(self, root=""):
        self.root = Path(root) if root else None
        self.rows = []
        self.conf = {}

    def p(self, path):
        return (self.root / str(path).lstrip("/")) if self.root else Path(path)

    def add(self, status, what, detail=""):
        self.rows.append((status, what, detail))

    # ---------------------------------------------------------------- checks
    def system(self):
        osr = {}
        try:
            for line in self.p("/etc/os-release").read_text().splitlines():
                k, _, v = line.partition("=")
                osr[k] = v.strip('"')
        except OSError:
            pass
        self.add(INFO, "system", osr.get("PRETTY_NAME") or osr.get("NAME", "unknown"))
        mk = shutil.which("grub2-mkconfig") or shutil.which("grub-mkconfig")
        ver = ""
        if mk:
            r = subprocess.run([mk, "--version"], capture_output=True, text=True)
            ver = r.stdout.strip()
        self.add(INFO, "grub", ver or "grub-mkconfig not found")
        self.add(INFO, "boot mode", "UEFI" if Path("/sys/firmware/efi").exists() else "BIOS (or unknown)")
        self.add(INFO, "python", f"{sys.version.split()[0]} ({sys.executable})")
        gfx = ""
        try:
            for line in self.p("/etc/default/grub").read_text().splitlines():
                m = re.match(r"^GRUB_GFXMODE=(\S+)", line)
                if m:
                    gfx = m.group(1)
        except OSError:
            pass
        self.add(INFO, "GRUB_GFXMODE", gfx or "not set")
        return gfx

    def config(self):
        path = self.p("/etc/material-grub.conf")
        if not path.is_file():
            self.add(WARN, "config", f"{path} does not exist (defaults are used)")
            return mgrub.load_conf(str(path))
        problems = []
        for n, line in enumerate(path.read_text().splitlines(), 1):
            s = line.split("#", 1)[0].strip()
            if not s:
                continue
            m = re.match(r'^([A-Za-z_]+)\s*=\s*"?([^"]*?)"?$', s)
            if not m:
                problems.append(f"line {n}: cannot read {s!r}")
                continue
            k, v = m.group(1), m.group(2).strip()
            if k not in mgrub.CONF_DEFAULTS:
                problems.append(f"line {n}: unknown key {k}")
            elif k == "TIMEOUT" and not (v.isdigit() or v == ""):
                problems.append(f"line {n}: TIMEOUT must be a number, got {v!r}")
            elif k in mgrub.CONF_CHOICES and v.lower() not in mgrub.CONF_CHOICES[k]:
                problems.append(f"line {n}: {k}={v} (allowed: {', '.join(mgrub.CONF_CHOICES[k])})")
            elif (
                k not in mgrub.CONF_CHOICES
                and k != "TIMEOUT"
                and v.lower() not in ("on", "off", "yes", "no", "true", "false", "1", "0")
            ):
                problems.append(f"line {n}: {k}={v} (expected on or off)")
        conf = mgrub.load_conf(str(path))
        if problems:
            self.add(WARN, "config", f"{path}: " + "; ".join(problems))
        else:
            self.add(OK, "config", f"{path} is valid (STYLE={conf['STYLE']}, SCHEME={conf['SCHEME']})")
        return conf

    def overrides(self, pkg):
        path = self.p(str(mgoverrides.path()) if not self.root else "/etc/material-grub/overrides.json")
        if not path.is_file():
            self.add(INFO, "overrides", "none (no custom colours, names, icons or order)")
            return
        ov, problems = mgoverrides.load(path)
        if problems and ov == mgoverrides.DEFAULTS:
            self.add(WARN, "overrides", "ignored, the defaults are used: " + "; ".join(problems))
            return
        missing = []
        for r in ov["entries"]:
            ic = r.get("icon", "")
            if ic.startswith("file:") and not (path.parent / "icons" / ic[5:]).is_file():
                missing.append(ic[5:])
            elif ic and not ic.startswith("file:") and pkg and not (pkg / "glyphs" / f"{ic}.png").is_file():
                missing.append(ic)
        if missing:
            self.add(WARN, "overrides", "icons not found, the default ones are used: " + ", ".join(missing))
            return
        meta = self.p("/var/lib/material-grub/cfg-meta.json") if self.root else mgsafe.state_dir() / "cfg-meta.json"
        try:
            applied = json.loads(meta.read_text()).get("layout")
        except (OSError, ValueError):
            applied = None
        if applied is not None and applied != mgoverrides.layout_sha(ov):
            self.add(
                WARN,
                "overrides",
                "the order or hidden entries changed since grub.cfg was generated: run sudo material-grub apply",
            )
            return
        n = len(ov["entries"])
        mode = "single colour " + ov["seed"]["color"] if ov["seed"]["mode"] == "single" else "per-entry colours"
        self.add(OK, "overrides", f"{path} is valid ({n} entr{'y' if n == 1 else 'ies'} customised, {mode})")

    def package(self, here):
        pkg = self.p(os.environ.get("MATERIAL_PKG") or "/usr/share/material-grub")
        immutable = self.p("/var/lib/material-grub/pkg")
        if not pkg.is_dir() and immutable.is_dir():
            pkg = immutable
        if not (pkg / "res").is_dir():
            self.add(FAIL, "package", f"{pkg} is not an installed theme package (run the installer)")
            return None
        v = (pkg / "VERSION").read_text().strip() if (pkg / "VERSION").is_file() else "unknown (installed before 0.6.0)"
        self.add(INFO, "installed version", v)
        source = here.parent.parent / "VERSION"
        if source.is_file() and source.read_text().strip() != v and (pkg / "VERSION").is_file():
            self.add(
                WARN,
                "version",
                f"this checkout is {source.read_text().strip()} but {v} is installed: run sudo ./install.sh",
            )
        elif source.is_file() and not (pkg / "VERSION").is_file():
            self.add(
                WARN,
                "version",
                f"this checkout is {source.read_text().strip()}; the installed package predates version stamps: run sudo ./install.sh",
            )
        return pkg

    def boot_unreadable(self):
        """True when a GRUB directory exists but this user may not look inside it (Fedora makes /boot/grub2 0700)."""
        for d in ("/boot/grub2", "/boot/grub"):
            p = self.p(d)
            if p.is_dir() and not os.access(p, os.R_OK | os.X_OK):
                return True
        return False

    def theme(self, pkg, gfx):
        found = [d for d in ("/boot/grub2/themes/material", "/boot/grub/themes/material") if self.p(d).is_dir()]
        if not found and self.boot_unreadable():
            self.add(WARN, "theme", "/boot/grub2 is root-only (Fedora does this): run with sudo to check the theme")
            return None
        if not found:
            self.add(FAIL, "theme", "no theme directory in /boot/grub2/themes or /boot/grub/themes")
            return None
        theme = self.p(found[0])
        problems = mgsafe.theme_problems(theme, pkg)
        if problems:
            self.add(FAIL, "theme", f"{theme} is incomplete: " + "; ".join(problems))
        else:
            self.add(OK, "theme", f"{theme} is complete")
        self.resolution(theme, pkg, gfx)
        return theme

    def resolution(self, theme, pkg, gfx):
        """The theme is pixel-bound: it has to be written for the mode GRUB_GFXMODE names, and that mode should be the screen's own. The first is what apply
        fixes; the second only the user can (the firmware decides which modes exist)."""
        want = mgtheme.first_mode(gfx) or (None if gfx and gfx.split(",")[0] not in ("", "auto") else (1920, 1080))
        try:
            have = (theme / ".mode").read_text().strip()
        except OSError:
            have = None
        if have is None:  # a theme written by an older version: it is for the closest built-in size
            if want:
                best = mgrub.snap(f"{want[0]}x{want[1]}", [p.name for p in (pkg / "res").iterdir()])
                self.add(
                    WARN,
                    "resolution",
                    f"the theme was written by an older version (for {best}); run sudo material-grub apply to write it for exactly {want[0]}x{want[1]}",
                )
            return
        if have == "auto":
            self.add(
                INFO,
                "resolution",
                f"the basic theme (it fits any screen) is installed: GRUB_GFXMODE={gfx or 'not set'} is not a usable mode",
            )
            return
        if want and have != f"{want[0]}x{want[1]}":
            self.add(
                FAIL,
                "resolution",
                f"the theme is written for {have}, but GRUB_GFXMODE={gfx or 'not set'} asks for {want[0]}x{want[1]}: run sudo material-grub apply",
            )
            return
        native = mgtheme.native_mode(str(self.p("/sys/class/drm")))
        if native and f"{native[0]}x{native[1]}" != have:
            self.add(
                WARN,
                "resolution",
                f"the theme is written for {have} but your screen is {native[0]}x{native[1]}: if the menu does not fill the screen, set GRUB_GFXMODE={native[0]}x{native[1]} in /etc/default/grub and run sudo material-grub apply",
            )
        else:
            self.add(
                OK,
                "resolution",
                f"the theme is written for exactly {have}" + (" (your screen's size)" if native else ""),
            )

    def grub_cfg(self):
        found = [f for f in ("/boot/grub2/grub.cfg", "/boot/grub/grub.cfg") if self.p(f).exists()]
        if not found and self.boot_unreadable():
            self.add(WARN, "grub.cfg", "/boot/grub2 is root-only (Fedora does this): run with sudo to check grub.cfg")
            return None
        if not found:
            self.add(FAIL, "grub.cfg", "not found in /boot/grub2 or /boot/grub")
            return None
        cfg = self.p(found[0])
        try:
            text = cfg.read_text(errors="replace")
        except PermissionError:
            self.add(WARN, "grub.cfg", f"{cfg} is not readable: run with sudo for the full report")
            return None
        self.add(
            OK if MARK in text else FAIL,
            "grub.cfg annotated",
            f"{cfg}" + ("" if MARK in text else " has not been processed: run sudo material-grub apply"),
        )
        ok, msgs = mgsafe.check_script(cfg)
        self.add(OK if ok else FAIL, "grub.cfg valid", "passes the GRUB script check" if ok else "; ".join(msgs))
        guarded = "theme.txt -a -d" in text or not re.search(r"^set theme=", text, re.M)
        self.add(
            OK if guarded else WARN,
            "theme guard",
            "the menu falls back to plain GRUB when the theme is missing"
            if guarded
            else "set theme is not guarded (re-run the installer)",
        )
        return cfg

    def scenes(self, theme, pkg):
        state = mgsafe.state_dir() / "entries.json" if not self.root else self.p("/var/lib/material-grub/entries.json")
        if not state.is_file() or theme is None:
            self.add(WARN, "scenes", f"no entry state at {state}" if not state.is_file() else "no theme to look in")
            return
        entries = json.loads(state.read_text())
        classes = json.loads((pkg / "classes.json").read_text()) if (pkg / "classes.json").is_file() else {}
        missing = []
        for e in entries:
            cls = e.get("class", "")
            if cls.startswith("mg_") and e.get("kind") in ("kernel", "rescue", "advanced"):
                name = cls
            else:
                name = (classes.get(e.get("key"), [e.get("key")]) or [e.get("key")])[0]
            if not (theme / "icons" / f"{name}.png").is_file():
                missing.append(e.get("title", name))
        if missing:
            self.add(
                FAIL,
                "scenes",
                f"{len(missing)} of {len(entries)} menu entries have no scene (first: {missing[0]}): run sudo material-grub apply",
            )
        else:
            self.add(OK, "scenes", f"every one of the {len(entries)} menu entries has a scene")

    def hooks(self):
        immutable = (self.p("/var/lib/material-grub/env").is_file()) and "MG_IMMUTABLE=1" in self.p(
            "/var/lib/material-grub/env"
        ).read_text()
        want = [("/usr/local/bin/material-grub", True)]
        if immutable:
            want.append(("/var/lib/material-grub/postprocess", True))
        else:
            want += [(f"/etc/grub.d/{h}", True) for h in HOOKS] + [("/usr/libexec/material-grub-postprocess", True)]
        bad = []
        for f, must_exec in want:
            p = self.p(f)
            if not p.is_file():
                bad.append(f"{f} is missing")
            elif must_exec and not os.access(p, os.X_OK):
                bad.append(f"{f} is not executable")
        self.add(
            FAIL if bad else OK,
            "hooks",
            "; ".join(bad)
            if bad
            else f"{len(want)} files installed and executable" + (" (immutable layout)" if immutable else ""),
        )

    def path_unit(self):
        if self.root or not shutil.which("systemctl") or not Path("/run/systemd/system").exists():
            self.add(INFO, "path unit", "systemd is not running here: re-run the installer after kernel changes")
            return
        r = {
            k: subprocess.run(["systemctl", k, "material-grub.path"], capture_output=True, text=True).stdout.strip()
            for k in ("is-enabled", "is-active")
        }
        good = r["is-enabled"] == "enabled" and r["is-active"] == "active"
        self.add(
            OK if good else FAIL,
            "path unit",
            f"material-grub.path is {r['is-enabled']} and {r['is-active']}"
            + ("" if good else ": run sudo systemctl enable --now material-grub.path"),
        )

    def last_error(self):
        f = self.p("/var/lib/material-grub/last-error") if self.root else mgsafe.state_dir() / "last-error"
        if not f.is_file():
            self.add(OK, "last error", "none")
            return
        try:
            d = json.loads(f.read_text())
            self.add(
                FAIL, "last error", f"{d.get('time', '?')}: {d.get('reason', '')}: " + "; ".join(d.get("details", []))
            )
        except ValueError:
            self.add(FAIL, "last error", f"{f} exists but cannot be read")

    # ---------------------------------------------------------------- run
    def summary(self):
        """One object for the GUI, built from the rows of a finished run()."""
        row = {w: (s, x) for s, w, x in self.rows}
        ver = row.get("installed version", (None, ""))[1]
        theme = row.get("theme", (None, ""))[0]
        return {
            "installed": "installed version" in row and theme == OK,
            "version": ver or None,
            "style": self.conf.get("STYLE"),
            "scheme": self.conf.get("SCHEME"),
            "config": self.conf,
            "failed": sum(1 for r in self.rows if r[0] == FAIL),
            "warnings": sum(1 for r in self.rows if r[0] == WARN),
            "last_error": None if row.get("last error", (OK,))[0] == OK else row["last error"][1],
            "checks": [{"status": s, "check": w, "detail": x} for s, w, x in self.rows],
        }

    def run(self, here):
        gfx = self.system()
        self.conf = self.config()
        pkg = self.package(here)
        self.overrides(pkg)
        self.hooks()
        self.path_unit()
        if pkg:
            theme = self.theme(pkg, gfx)
            self.grub_cfg()
            self.scenes(theme, pkg)
        self.last_error()
        return not any(s == FAIL for s, _, _ in self.rows)

    def render(self):
        w = max(len(r[1]) for r in self.rows)
        lines = ["material-grub doctor", ""]
        for s, what, detail in self.rows:
            lines.append(f"  [{s:^4}] {what.ljust(w)}  {detail}")
        bad = sum(1 for r in self.rows if r[0] == FAIL)
        warn = sum(1 for r in self.rows if r[0] == WARN)
        lines += ["", f"{bad} failed, {warn} warning(s)" if bad or warn else "everything is fine"]
        return "\n".join(lines)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = argv[argv.index("--root") + 1] if "--root" in argv else ""
    d = Doctor(root)
    ok = d.run(Path(__file__).resolve())
    if "--status-json" in argv:
        print(json.dumps(d.summary(), indent=1))
    elif "--json" in argv:
        print(json.dumps([{"status": s, "check": w, "detail": x} for s, w, x in d.rows], indent=1))
    else:
        print(d.render())
    return 0 if ok else 1
