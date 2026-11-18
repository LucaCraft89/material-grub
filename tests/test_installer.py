"""Tests for the installer: option parsing, settings, answers, the resolution rules and the sh bootstrap (with fake Python and package managers).
No root, no package manager, nothing installed. usage: python3 tests/test_installer.py"""

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "install"))
import installer  # noqa: E402


def make(argv):
    i = installer.Installer(argv)
    i.parse()
    return i


class Parse(unittest.TestCase):
    def test_defaults(self):
        i = make([])
        self.assertEqual((i.res, i.scheme, i.style, i.imm, i.stage, i.deps), ("", "dark", "", False, False, True))

    def test_flags(self):
        i = make(
            [
                "--res",
                "2560x1440",
                "--style",
                "list",
                "--scheme",
                "light",
                "--no-hints",
                "--no-cookie",
                "--logo",
                "--yes",
                "--stage-only",
            ]
            + ["--no-deps", "--pkg", "/x", "--dist-out", "/y", "--keep-build", "--immutable", "--force", "--tui"]
        )
        self.assertEqual((i.res, i.style, i.scheme, i.scheme_set), ("2560x1440", "list", "light", True))
        self.assertEqual((i.hints, i.hints_set, i.cookie, i.logo), (False, True, "off", "on"))
        self.assertEqual(
            (i.yes, i.stage, i.deps, i.prebuilt, i.distout, i.keep, i.imm, i.force, i.tuimode),
            (True, True, False, "/x", "/y", True, True, True, "force"),
        )

    def test_ventoy_optional_mount_point(self):
        self.assertEqual(make(["--ventoy", "/run/media/u/V", "--mode", "snapshot"]).stick, "/run/media/u/V")
        i = make(["--ventoy", "--style", "list"])
        self.assertEqual((i.ventoy, i.stick, i.style), (True, "", "list"))

    def test_dry_run_implies_no_deps(self):
        i = make(["--dry-run"])
        self.assertEqual((i.dry, i.deps), (True, False))

    def test_bad_values_exit_2(self):
        for bad in (["--style", "wild"], ["--scheme", "pink"], ["--mode", "x"], ["--frobnicate"]):
            with self.assertRaises(SystemExit) as c:
                make(bad)
            self.assertEqual(c.exception.code, 2, bad)

    def test_help_text_is_the_header_of_install_sh(self):
        r = subprocess.run(
            [sys.executable, str(ROOT / "install/installer.py"), "--help"], capture_output=True, text=True
        )
        sh = subprocess.run(["sh", str(ROOT / "install.sh"), "--help"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, sh.stdout)
        self.assertIn("--dry-run", r.stdout)
        self.assertNotIn("set -eu", r.stdout)


class Settings(unittest.TestCase):
    def test_settings_from_flags(self):
        i = make(["--style", "list", "--no-cookie", "--no-hints", "--scheme", "light"])
        i.info = lambda *_: None
        i.build_settings()
        self.assertEqual(
            i.confsets, [("STYLE", "list"), ("COOKIE", "off"), ("LOGO", "off"), ("HINTS", "off"), ("SCHEME", "light")]
        )
        self.assertEqual(i.confset_args()[:2], ["--set", "STYLE=list"])

    def test_answers_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".ans", delete=False) as f:
            f.write(
                "RES='2560x1440'\nSTYLE='clean'\nSCHEME='light'\nHINTS='off'\nTIMEOUT='7'\nRAW_NAME='off'\nTARGET='ventoy'\nSTICK='/mnt/V'\nRESX='1920x1080'\n"
            )
        a = installer.Installer.read_answers(f.name)
        os.unlink(f.name)
        self.assertEqual(a["RES"], "2560x1440")
        self.assertEqual(a["STICK"], "/mnt/V")
        i = make([])
        i.apply_answers(a)
        self.assertEqual(
            (i.res, i.style, i.scheme, i.hints, i.ventoy, i.stick, i.tuiran),
            ("2560x1440,1920x1080", "clean", "light", False, True, "/mnt/V", True),
        )
        self.assertIn(("TIMEOUT", "7"), i.confsets)
        self.assertIn(("RAW_NAME", "off"), i.confsets)

    def test_missing_stick_fails_early(self):
        i = make(["--ventoy", "--style", "list"])
        with self.assertRaises(SystemExit):
            i.build_settings()


class Resolution(unittest.TestCase):
    def test_snap_and_list(self):
        i = make(["--res", "1600x1000"])
        i.info = lambda *_: None
        i.resolution()
        self.assertEqual(i.build_res, "1920x1200")

    def test_several_resolutions_only_for_ventoy(self):
        i = make(["--res", "1920x1080,2560x1440"])
        i.info = lambda *_: None
        with self.assertRaises(SystemExit):
            i.resolution()
        v = make(["--ventoy", "/m", "--res", "1920x1080,2560x1440"])
        v.info = lambda *_: None
        v.resolution()
        self.assertEqual(v.build_res, "1920x1080,2560x1440")

    def test_bad_resolution(self):
        i = make(["--res", "big"])
        i.info = lambda *_: None
        with self.assertRaises(SystemExit):
            i.resolution()


class Bootstrap(unittest.TestCase):
    """install.sh with fake interpreters and package managers on a private PATH."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.bin = self.d / "bin"
        self.bin.mkdir()
        self.log = self.d / "log.txt"
        for tool in ("sh", "sed", "id", "dirname", "env", "cat", "printf", "true", "false", "echo"):
            src = next((Path(p) / tool for p in ("/usr/bin", "/bin") if (Path(p) / tool).exists()), None)
            if src:
                (self.bin / tool).symlink_to(src)

    def tearDown(self):
        self.tmp.cleanup()

    def shim(self, name, body):
        p = self.bin / name
        p.write_text("#!/bin/sh\n" + body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)

    def python_shim(self, name, version_ok):
        # `-c` is the version probe; anything else is the installer being started
        self.shim(
            name,
            f'if [ "$1" = -c ]; then exit {0 if version_ok else 1}; fi\necho "REACHED {name} $*" >> {self.log}\nexit 0\n',
        )

    def run_boot(self, root=False, *args):
        env = {"PATH": str(self.bin), "HOME": str(self.d)}
        return subprocess.run(["sh", str(ROOT / "install.sh"), *args], capture_output=True, text=True, env=env)

    def test_uses_a_good_python3(self):
        self.python_shim("python3", True)
        r = self.run_boot(False, "--stage-only")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("REACHED python3", self.log.read_text())
        self.assertIn("install/installer.py --stage-only", self.log.read_text())

    def test_old_python3_is_skipped_for_a_versioned_one(self):
        self.python_shim("python3", False)  # RHEL 8: python3 is 3.6
        self.python_shim("python3.11", True)
        r = self.run_boot(False)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("REACHED python3.11", self.log.read_text())

    def test_help_needs_no_python(self):
        r = self.run_boot(False, "--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("--dry-run", r.stdout)

    def test_no_python_and_no_root_says_so(self):
        if os.geteuid() == 0:
            self.skipTest("running as root")
        r = self.run_boot(False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("Python 3.8 or newer is needed", r.stderr)
        self.assertIn("sudo ./install.sh", r.stderr)

    @unittest.skipUnless(os.geteuid() == 0, "needs root: the bootstrap installs Python only as root")
    def test_installs_python_with_the_package_manager(self):  # pragma: no cover (CI containers run this as root)
        self.shim(
            "dnf",
            f'echo "dnf $*" >> {self.log}\nif [ "$2" = python39 ]; then cp {self.bin}/python3.9.real {self.bin}/python3.9; fi\n',
        )
        self.python_shim("python3.9.real", True)
        self.python_shim("python3", False)
        r = self.run_boot(True)
        self.assertEqual(r.returncode, 0, r.stderr)
        log = self.log.read_text()
        self.assertLess(log.index("dnf install -y python3"), log.index("dnf install -y python39"))
        self.assertIn("REACHED python3.9.real" if False else "REACHED python3.9", log)


class FromPackage(unittest.TestCase):
    def test_failure_never_fails_the_transaction(self):
        import contextlib
        import io

        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = installer.Installer(["--from-package", "--pkg", "/nonexistent", "--res", "1920x1080"]).main()
        self.assertEqual(rc, 0)
        if os.geteuid() != 0:
            self.assertIn("could not finish", err.getvalue())

    def test_flags(self):
        i = make(["--from-package"])
        self.assertEqual((i.from_package, i.yes, i.deps, i.tuimode), (True, True, False, "no"))


class ShellStatic(unittest.TestCase):
    def test_bootstrap_is_posix_sh(self):
        for f in ("install.sh", "install/install.sh", "install/uninstall.sh"):
            self.assertEqual(subprocess.run(["sh", "-n", str(ROOT / f)]).returncode, 0, f)
        text = (ROOT / "install.sh").read_text()
        self.assertTrue(text.startswith("#!/bin/sh"))
        self.assertNotIn("[[", text)
        self.assertLess(len(text.splitlines()), 80, "the bootstrap must stay tiny")


if __name__ == "__main__":
    unittest.main()
