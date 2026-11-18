"""Safety net tests: validate the rewritten grub.cfg, roll back when it is wrong, notify, do not loop.
Needs a built package (dist/material-grub). usage: python3 tests/test_safety.py"""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "dist/material-grub"
BIN = ROOT / "install/bin"
GOLD = ROOT / "tests/golden"
sys.path.insert(0, str(BIN))
import mgsafe  # noqa: E402

GOOD = "set timeout=5\nmenuentry 'Fedora Linux' --class fedora {\n\techo hi\n}\nmenuentry 'Windows 11' {\n}\n"


class Checks(unittest.TestCase):
    def test_structure(self):
        self.assertEqual(mgsafe.structure_problems(GOOD), [])
        self.assertTrue(mgsafe.structure_problems("menuentry 'x' {\n echo\n"))
        self.assertTrue(mgsafe.structure_problems("menuentry 'x' {\n}\n}\n"))
        self.assertEqual(mgsafe.structure_problems("menuentry 'a } {' {\n}\n"), [])

    def test_golden_files_pass(self):
        for n in ("debian", "ubuntu", "arch", "fedora"):
            self.assertEqual(mgsafe.structure_problems((GOLD / f"{n}.annotated.cfg").read_text()), [], n)

    def test_box(self):
        b = mgsafe.box("title", ["one", "two"])
        self.assertTrue(all(len(l) == len(b.split("\n")[0]) for l in b.split("\n")))
        self.assertIn("one", b)


@unittest.skipUnless((PKG / "res").is_dir(), "no built package")
class Guard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.cfg = self.d / "grub.cfg"
        self.cfg.write_text(GOOD)
        self.state = self.d / "state"
        self.theme = self.d / "themes/material"
        self.fakebin = self.d / "fakebin"
        self.fakebin.mkdir()
        self.calls = self.d / "calls.txt"
        for name in ("logger", "wall"):  # record the calls instead of writing to the journal / other terminals
            f = self.fakebin / name
            f.write_text(f'#!/bin/sh\necho "{name} $*" >> {self.calls}\ncat >/dev/null 2>&1 < /dev/null || true\n')
            f.chmod(f.stat().st_mode | stat.S_IEXEC)
        self.make_theme()
        self.pkg = self.d / "pkg"
        shutil.copytree(PKG, self.pkg, symlinks=True, ignore=shutil.ignore_patterns("res", "scenes"))
        os.symlink(PKG / "res", self.pkg / "res")
        os.symlink(PKG / "scenes", self.pkg / "scenes")

    def tearDown(self):
        self.tmp.cleanup()

    def make_theme(self):
        (self.theme / "icons").mkdir(parents=True, exist_ok=True)
        classes = json.loads((PKG / "classes.json").read_text())
        for names in classes.values():
            for n in names:
                (self.theme / "icons" / f"{n}.png").write_bytes(b"png")
        for n in ("theme.txt", "MG-Label.pf2", "MG-Raw.pf2"):
            (self.theme / n).write_bytes(b"x")
        (self.theme / ".aspect").write_text((PKG / "res/1920x1080/aspect").read_text())

    def run_pp(self, *extra, check_script=None, tty=False):
        env = dict(os.environ, MATERIAL_STATE_DIR=str(self.state), PATH=f"{self.fakebin}:{os.environ['PATH']}")
        env["MG_SCRIPT_CHECK"] = check_script if check_script is not None else ""
        cmd = [
            sys.executable,
            str(self.pkg / "bin/material-grub-postprocess"),
            "--pkg",
            str(self.pkg),
            "--cfg",
            str(self.cfg),
            "--theme",
            str(self.theme),
            *extra,
        ]
        return subprocess.run(cmd, capture_output=True, text=True, env=env)

    def break_classes_tool(self, body):
        t = self.pkg / "bin/material-grub-classes"
        t.unlink()
        t.write_text("#!/usr/bin/env python3\nimport sys\n" + body)

    def test_good_run_is_kept(self):
        r = self.run_pp()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("material-grub: classes applied", self.cfg.read_text())
        self.assertFalse((self.state / "last-error").exists())

    def test_broken_cfg_is_rolled_back(self):
        self.break_classes_tool("open(sys.argv[1], 'a').write(\"menuentry 'broken' {\\n\")\n")
        r = self.run_pp()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.cfg.read_text(), GOOD)  # byte for byte as before
        self.assertIn("rolled back", r.stderr)
        self.assertIn("never closed", r.stderr)
        err = json.loads((self.state / "last-error").read_text())
        self.assertIn("rolled back", err["reason"])
        self.assertIn("logger -t material-grub", self.calls.read_text())

    def test_failing_tool_is_rolled_back(self):
        self.break_classes_tool("open(sys.argv[1], 'w').write('garbage')\nsys.exit(3)\n")
        r = self.run_pp()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.cfg.read_text(), GOOD)

    def test_lost_entries_are_rolled_back(self):
        self.break_classes_tool(
            "open(sys.argv[1], 'w').write(\"# material-grub: classes applied\\nset timeout=5\\n\")\n"
        )
        r = self.run_pp()
        self.assertEqual(r.returncode, 1)
        self.assertIn("entries were lost", r.stderr)
        self.assertEqual(self.cfg.read_text(), GOOD)

    def test_external_checker_failure_is_rolled_back(self):
        checker = self.d / "check.sh"
        checker.write_text(
            "#!/bin/sh\ngrep -q 'classes applied' \"$1\" && { echo 'syntax error: unexpected' >&2; exit 1; }\nexit 0\n"
        )
        checker.chmod(0o755)
        r = self.run_pp(check_script=str(checker))
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.cfg.read_text(), GOOD)
        self.assertIn("syntax error: unexpected", r.stderr)

    def test_incomplete_theme_is_rolled_back(self):
        (self.theme / "MG-Raw.pf2").unlink()
        r = self.run_pp()
        self.assertEqual(r.returncode, 1)
        self.assertIn("MG-Raw.pf2 is missing", r.stderr)
        self.assertEqual(self.cfg.read_text(), GOOD)

    def test_missing_icons_are_rolled_back(self):
        shutil.rmtree(self.theme / "icons")
        r = self.run_pp()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.cfg.read_text(), GOOD)

    def test_wall_only_without_a_terminal(self):
        self.break_classes_tool("sys.exit(1)\n")
        self.run_pp()  # captured stderr: not a terminal
        self.assertIn("wall", self.calls.read_text())

    def test_no_retry_loop_on_the_same_input(self):
        self.break_classes_tool("sys.exit(1)\n")
        self.assertEqual(self.run_pp().returncode, 1)
        r = self.run_pp()  # the restore changed nothing: the path unit would start us again with the same file
        self.assertEqual(r.returncode, 0)
        self.assertIn("already failed validation", r.stderr)
        self.assertEqual(self.run_pp("--force").returncode, 1)  # an explicit retry runs again

    def test_new_input_is_tried_again_and_success_clears_the_note(self):
        self.break_classes_tool("sys.exit(1)\n")
        self.run_pp()
        shutil.copy(PKG / "bin/material-grub-classes", self.pkg / "bin/material-grub-classes")
        self.cfg.write_text(GOOD + "menuentry 'New kernel' {\n}\n")
        r = self.run_pp()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.state / "last-error").exists())

    def test_real_script_check_when_installed(self):
        real = mgsafe.script_checker() if os.environ.get("MG_SCRIPT_CHECK") is None else None
        if not real:
            self.skipTest("grub-script-check is not installed")
        ok, msgs = mgsafe.check_script(GOLD / "ubuntu.annotated.cfg")
        self.assertTrue(ok, msgs)
        bad = self.d / "bad.cfg"
        bad.write_text("menuentry 'x' {\n echo\n")
        self.assertFalse(mgsafe.check_script(bad)[0])


class BootGuard(unittest.TestCase):
    """GRUB must skip `set theme` when the theme is not there at boot."""

    def test_static_block_is_guarded(self):
        src = (BIN / "cmd_static.py").read_text()
        self.assertIn("if [ -f $prefix/themes/material/theme.txt -a -d $prefix/themes/material/icons ]; then", src)
        self.assertLess(src.index("if [ -f $prefix/themes/material/theme.txt"), src.index("set theme=$prefix"))

    def test_mkconfig_hook_is_guarded(self):
        src = (ROOT / "install/05_material").read_text()
        guard = src.index("-f (\\$root)$REL/theme.txt")
        self.assertLess(guard, src.index("set theme="))
        self.assertLess(guard, src.index("loadfont"))
        self.assertIn("\nfi\n", src)


if __name__ == "__main__":
    unittest.main()
