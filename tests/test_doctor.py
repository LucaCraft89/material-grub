"""Doctor tests on a staged installation (install.sh --dest) with a fake /boot: no root, nothing installed on this machine.
Needs a built package (dist/material-grub, 1920x1080). usage: python3 tests/test_doctor.py"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "dist/material-grub"
BIN = ROOT / "install/bin"
GOLD = ROOT / "tests/golden"


@unittest.skipUnless((PKG / "res/1920x1080").is_dir(), "no built package")
class Doctor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = Path(self.tmp.name)
        subprocess.run(
            [
                "sh",
                str(ROOT / "install/install.sh"),
                "--dest",
                str(self.r),
                "--no-run",
                "--pkg",
                str(PKG),
                "--res",
                "1920x1080",
            ],
            check=True,
            capture_output=True,
        )
        theme = self.r / "boot/grub2/themes/material"
        subprocess.run(
            [
                sys.executable,
                str(BIN / "material-grub-assemble"),
                "--mode",
                "1920x1080",
                "--pkg",
                str(PKG),
                "--out",
                str(theme),
            ],
            check=True,
            capture_output=True,
        )
        (self.r / "boot/grub2/grub.cfg").write_text((GOLD / "fedora.annotated.cfg").read_text())
        (self.r / "etc/default").mkdir(parents=True, exist_ok=True)
        (self.r / "etc/default/grub").write_text("GRUB_GFXMODE=1920x1080\n")
        self.state = self.r / "var/lib/material-grub"
        self.state.mkdir(parents=True, exist_ok=True)
        entries = [
            {"class": "mg_aaaaaaaaaa", "key": "fedora", "kind": "kernel", "title": "Fedora"},
            {"class": "mg_bbbbbbbbbb", "key": "windows11", "kind": "plain", "title": "Windows"},
        ]
        (self.state / "entries.json").write_text(json.dumps(entries))
        (theme / "icons/mg_aaaaaaaaaa.png").write_bytes(b"png")
        self.theme = theme

    def tearDown(self):
        self.tmp.cleanup()

    def doctor(self):
        env = {k: v for k, v in dict(os.environ, MG_SCRIPT_CHECK="").items() if k != "MATERIAL_PKG"}
        r = subprocess.run(
            [sys.executable, str(BIN / "material-grub-doctor"), "--root", str(self.r)],
            capture_output=True,
            text=True,
            env=env,
        )
        return r.returncode, r.stdout

    def test_healthy(self):
        code, out = self.doctor()
        self.assertEqual(code, 0, out)
        self.assertIn("everything is fine", out)
        self.assertIn("installed version", out)
        self.assertIn("every one of the 2 menu entries has a scene", out)

    def test_status_json(self):
        env = {k: v for k, v in dict(os.environ, MG_SCRIPT_CHECK="").items() if k != "MATERIAL_PKG"}
        r = subprocess.run(
            [sys.executable, str(BIN / "material-grub-doctor"), "--root", str(self.r), "--status-json"],
            capture_output=True,
            text=True,
            env=env,
        )
        d = json.loads(r.stdout)
        self.assertEqual((d["installed"], d["failed"]), (True, 0))
        self.assertEqual((d["style"], d["scheme"]), ("rail", "dark"))
        self.assertTrue(d["version"])
        self.assertIsNone(d["last_error"])
        self.assertTrue(any(c["check"] == "theme" for c in d["checks"]))
        (self.theme / "theme.txt").unlink()
        r = subprocess.run(
            [sys.executable, str(BIN / "material-grub-doctor"), "--root", str(self.r), "--status-json"],
            capture_output=True,
            text=True,
            env=env,
        )
        d = json.loads(r.stdout)
        self.assertEqual((d["installed"], d["failed"] > 0), (False, True))

    def test_missing_scene(self):
        (self.theme / "icons/mg_aaaaaaaaaa.png").unlink()
        code, out = self.doctor()
        self.assertEqual(code, 1)
        self.assertIn("1 of 2 menu entries have no scene", out)

    def test_hook_not_executable(self):
        (self.r / "etc/grub.d/05_material").chmod(0o644)
        code, out = self.doctor()
        self.assertEqual(code, 1)
        self.assertIn("05_material is not executable", out)

    def test_incomplete_theme(self):
        (self.theme / "theme.txt").unlink()
        code, out = self.doctor()
        self.assertEqual(code, 1)
        self.assertIn("theme.txt is missing", out)

    def test_unannotated_cfg(self):
        (self.r / "boot/grub2/grub.cfg").write_text("menuentry 'x' {\n}\n")
        code, out = self.doctor()
        self.assertEqual(code, 1)
        self.assertIn("has not been processed", out)

    def test_broken_cfg(self):
        (self.r / "boot/grub2/grub.cfg").write_text("# material-grub: classes applied\nmenuentry 'x' {\n")
        code, out = self.doctor()
        self.assertEqual(code, 1)
        self.assertIn("never closed", out)

    def test_config_problems_are_warnings(self):
        (self.r / "etc/material-grub.conf").write_text("STYLE=wild\nNOPE=1\nTIMEOUT=abc\nHINTS=maybe\n")
        code, out = self.doctor()
        self.assertEqual(code, 0, out)
        for want in ("STYLE=wild", "unknown key NOPE", "TIMEOUT must be a number", "HINTS=maybe"):
            self.assertIn(want, out)

    def test_last_error(self):
        (self.state / "last-error").write_text(
            json.dumps({"time": "t", "reason": "rolled back", "details": ["a step failed"]})
        )
        code, out = self.doctor()
        self.assertEqual(code, 1)
        self.assertIn("rolled back: a step failed", out)

    def test_resolution_mismatch(self):
        (self.r / "etc/default/grub").write_text("GRUB_GFXMODE=1920x1200\n")  # theme is 16:9, the screen is 16:10
        res = PKG / "res/1920x1200"
        if not res.is_dir():
            self.skipTest("package has no 1920x1200 bundle")
        code, out = self.doctor()
        self.assertEqual(code, 1)
        self.assertIn("GRUB_GFXMODE=1920x1200", out)


if __name__ == "__main__":
    unittest.main()
