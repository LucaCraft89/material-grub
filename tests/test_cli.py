"""The `material-grub` command: subcommands, a scratch /etc through the environment, and the menu on a pty. stdlib only. usage: python3 tests/test_cli.py"""

import json
import os
import pty
import select
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "install/bin/cmd_cli.py"
sys.path.insert(0, str(ROOT / "install/bin"))


class Cli(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.env = dict(
            os.environ,
            MATERIAL_OVERRIDES=str(self.d / "etc/material-grub/overrides.json"),
            MATERIAL_CONF=str(self.d / "mg.conf"),
            MATERIAL_PKG=str(self.d / "nopkg"),
        )
        (self.d / "mg.conf").write_text("STYLE=rail\n")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.d, ignore_errors=True)

    def mg(self, *a, inp=None):
        r = subprocess.run(
            [sys.executable, str(CLI), *a],
            capture_output=True,
            text=True,
            env=self.env,
            input=inp,
            stdin=None if inp else subprocess.DEVNULL,
        )
        return r.returncode, r.stdout + r.stderr

    def test_help_version_unknown(self):
        rc, out = self.mg("help")
        self.assertEqual(rc, 0)
        for word in ("doctor", "apply", "gui", "colour", "presets", "ventoy", "uninstall"):
            self.assertIn(word, out)
        self.assertEqual(self.mg("--version")[1].split()[0], "material-grub")
        rc, out = self.mg("nonsense")
        self.assertEqual(rc, 2)
        self.assertIn("unknown command", out)

    def test_no_arguments_without_a_terminal_prints_the_help(self):
        rc, out = self.mg()
        self.assertEqual(rc, 0)
        self.assertIn("material-grub doctor", out)

    def test_colour(self):
        rc, out = self.mg("colour")
        self.assertIn("every entry its own colour", out)
        self.assertEqual(self.mg("colour", "#7e57c2")[0], 0)
        self.assertIn("one seed colour #7E57C2", self.mg("colour")[1])
        self.assertEqual(self.mg("colour", "forest")[0], 0)
        self.assertIn("#0B3D2E (Forest)", self.mg("colour")[1])
        self.assertEqual(self.mg("colour", "multi")[0], 0)
        self.assertIn("every entry its own colour", self.mg("colour")[1])
        self.assertEqual(self.mg("colour", "not-a-colour")[0], 2)
        ov = json.loads((self.d / "etc/material-grub/overrides.json").read_text())
        self.assertEqual(ov["seed"]["mode"], "multi")

    def test_overrides_and_conf(self):
        self.assertIn("nothing is customised", self.mg("overrides", "check")[1])
        self.mg("colour", "#112233")
        rc, out = self.mg("overrides", "check")
        self.assertEqual((rc, out.strip()), (0, "valid"))
        (self.d / "etc/material-grub/overrides.json").write_text('{"seed": {"mode": "no"}}')
        rc, out = self.mg("overrides", "check")
        self.assertEqual(rc, 1)
        self.assertIn("seed.mode", out)
        self.assertEqual(self.mg("conf", "STYLE=list")[0], 0)
        self.assertIn("STYLE=list", self.mg("conf")[1])
        self.assertEqual(self.mg("conf", "STYLE=neon")[0], 1)
        self.assertEqual(self.mg("conf", "NOPE")[0], 2)

    def test_presets(self):
        self.mg("colour", "#7E57C2")
        self.assertEqual(self.mg("presets", "save", "My look")[0], 0)
        self.assertIn("My look", self.mg("presets", "list")[1])
        self.mg("colour", "multi")
        self.assertEqual(self.mg("presets", "apply", "My look")[0], 0)
        self.assertIn("#7E57C2", self.mg("colour")[1])
        f = self.d / "out.json"
        self.assertEqual(self.mg("presets", "export", "My look", str(f))[0], 0)
        self.assertEqual(self.mg("presets", "delete", "My look")[0], 0)
        self.assertEqual(self.mg("presets", "import", str(f))[0], 0)
        self.assertIn("My look", self.mg("presets", "list")[1])
        self.assertEqual(self.mg("presets", "save", "../evil")[0], 1)
        bad = self.d / "bad.json"
        bad.write_text('{"preset": 1, "name": "x", "conf": {"EVIL": "1"}}')
        self.assertEqual(self.mg("presets", "import", str(bad))[0], 1)

    def test_gui_missing_is_explained(self):
        env = dict(self.env, PATH="/nonexistent")
        r = subprocess.run(
            [sys.executable, str(CLI), "gui"], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("--with-gui", r.stdout)

    def test_update_without_network_check(self):
        rc, out = self.mg("update")
        self.assertIn("installed: Material GRUB", out)

    def test_ventoy_without_a_stick(self):
        rc, out = self.mg("ventoy")
        self.assertIn("No mounted Ventoy stick", out)

    def test_menu_on_a_terminal(self):
        pid, fd = pty.fork()
        if pid == 0:
            os.environ.update(self.env)
            os.environ["TERM"] = "xterm"
            os.execv(sys.executable, [sys.executable, str(CLI)])
        os.set_blocking(fd, False)
        buf = b""
        t = time.time()
        sent = False
        while time.time() - t < 10:
            r, _, _ = select.select([fd], [], [], 0.2)
            if r:
                try:
                    buf += os.read(fd, 65536)
                except OSError:
                    break
            if not sent and b"Quit" in buf:
                os.write(fd, b"q")
                sent = True
            try:
                p, st = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                break
            if p:
                self.assertEqual(os.waitstatus_to_exitcode(st), 0)
                break
        else:
            os.kill(pid, 9)
            self.fail("the menu did not quit")
        text = buf.decode(errors="replace")
        for word in ("Health check", "Apply changes", "Open the GUI", "Presets", "Ventoy stick", "Uninstall"):
            self.assertIn(word, text)


if __name__ == "__main__":
    unittest.main()
