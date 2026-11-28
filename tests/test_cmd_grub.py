"""`material-boot grub ...` (install/bin/cmd_grub.py): the commands of the part, the words of the old `material-grub` command that moved, and that the old command is
not installed any more. Needs material-boot-core (next to the checkout, or MATERIAL_LIB). stdlib only. usage: python3 tests/test_cmd_grub.py"""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CMD = ROOT / "install/bin/cmd_grub.py"
sys.path.insert(0, str(ROOT / "install/bin"))


class Commands(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.env = dict(
            os.environ,
            MATERIAL_OVERRIDES=str(self.d / "etc/material-grub/overrides.json"),
            MATERIAL_CONF=str(self.d / "mg.conf"),
            MATERIAL_PKG=str(self.d / "nopkg"),
        )

    def tearDown(self):
        import shutil

        shutil.rmtree(self.d, ignore_errors=True)

    def mg(self, *a):
        r = subprocess.run(
            [sys.executable, str(CMD), *a], capture_output=True, text=True, env=self.env, stdin=subprocess.DEVNULL
        )
        return r.returncode, r.stdout + r.stderr

    def test_help_lists_the_commands_of_the_part(self):
        rc, out = self.mg("help")
        self.assertEqual(rc, 0)
        for word in ("apply", "doctor", "preview", "ventoy", "uninstall"):
            self.assertIn(f"material-boot grub {word}", out)
        self.assertNotIn("material-grub ", out.replace("material-grub.conf", ""))

    def test_no_arguments_print_the_help(self):
        rc, out = self.mg()
        self.assertEqual(rc, 0)
        self.assertIn("material-boot grub apply", out)

    def test_the_words_of_the_old_command_say_where_they_went(self):
        for word, where in (
            ("gui", "material-boot ui"),
            ("colour", "material-boot core colour"),
            ("presets", "material-boot core presets"),
            ("overrides", "material-boot core overrides"),
            ("conf", "material-boot core conf"),
            ("update", "material-boot core install"),
            ("version", "material-boot version"),
        ):
            rc, out = self.mg(word)
            self.assertEqual(rc, 2, word)
            self.assertIn(f"'{word}' moved: use  {where}", out)

    def test_an_unknown_word_is_unknown(self):
        rc, out = self.mg("nonsense")
        self.assertEqual(rc, 2)
        self.assertIn("unknown command 'nonsense'", out)
        self.assertNotIn("moved", out)

    def test_apply_without_root_says_how(self):
        if os.geteuid() == 0:
            self.skipTest("running as root")
        rc, out = self.mg("apply")  # no terminal: no sudo is attempted
        self.assertNotEqual(rc, 0)
        self.assertIn("sudo material-boot grub apply", out)

    def test_ventoy_without_a_stick(self):
        rc, out = self.mg("ventoy")
        self.assertIn("No mounted Ventoy stick", out)
        self.assertIn("material-boot grub ventoy /run/media", out)

    def test_a_reader_that_closes_the_pipe_is_not_an_error(self):
        """`material-boot grub help | grep -q x`: the reader is gone before the output is written; no traceback."""
        p = subprocess.Popen(
            [
                sys.executable,
                "-c",
                f"import time; time.sleep(0.8); import runpy, sys; sys.argv=[{str(CMD)!r}, 'help']; runpy.run_path({str(CMD)!r}, run_name='__main__')",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
            stdin=subprocess.DEVNULL,
        )
        p.stdout.close()  # the reader leaves before anything is written
        err = p.stderr.read()
        p.wait()
        self.assertNotIn("Traceback", err)
        self.assertNotIn("BrokenPipe", err)

    def test_doctor_asks_sudo_when_boot_is_root_only(self):
        # Fedora's /boot/grub2 is 0700: in a terminal doctor re-runs itself under sudo, in a script it just warns
        import contextlib
        import unittest.mock as mock

        import cmd_grub

        def run(tty):
            with contextlib.ExitStack() as st:
                st.enter_context(mock.patch.object(cmd_grub, "boot_root_only", return_value=True))
                st.enter_context(mock.patch.object(cmd_grub.sys.stdin, "isatty", return_value=tty))
                st.enter_context(mock.patch.object(cmd_grub.shutil, "which", return_value="/usr/bin/sudo"))
                st.enter_context(mock.patch("cmd_doctor.main", return_value=0))
                el = st.enter_context(mock.patch.object(cmd_grub, "elevate"))
                cmd_grub.c_doctor(["--json"])
                return el

        run(True).assert_called_once_with(["doctor", "--json"])
        run(False).assert_not_called()


class NoOldCommand(unittest.TestCase):
    def test_the_installer_puts_nothing_on_the_path_and_removes_the_old_command(self):
        install = (ROOT / "install/install.sh").read_text()
        self.assertEqual(re.findall(r'install -m755 "[^"]+" "\$D(/usr/local/s?bin/[\w.-]+)"', install), [])
        self.assertIn('"$D/usr/local/bin/material-grub"', install)  # removed, as the leftover of 1.1 and older
        self.assertFalse((ROOT / "install/material-grub").exists())

    def test_the_hooks_that_run_after_a_kernel_change_call_material_boot(self):
        for f in ("packaging/debian/kernel-hook", "packaging/arch/material-grub.hook"):
            text = (ROOT / f).read_text()
            self.assertIn("material-boot", text, f)
            self.assertIn("grub apply", text, f)
            self.assertNotRegex(text, r"/usr/local/bin/material-grub\b(?!-)", f)

    def test_nothing_else_calls_the_old_command(self):
        pat = re.compile(r"(?<![\w/.-])material-grub (apply|doctor|gui|colour|update|presets|overrides|conf)\b")
        for f in list((ROOT / "install").rglob("*")) + list((ROOT / "scripts").rglob("*")):
            if not f.is_file() or f.suffix in (".png", ".pyc") or "__pycache__" in f.parts:
                continue
            try:
                text = f.read_text()
            except UnicodeDecodeError:
                continue
            for m in pat.finditer(text):
                self.fail(f"{f.relative_to(ROOT)} still tells people to run `{m.group(0)}`")


if __name__ == "__main__":
    unittest.main()
