"""Screen-size handling: parsing of modes, the theme written for an exact size, centring, the basic fallback, and what the assemble step prints.
usage: python3 tests/test_mgtheme.py   (the assemble cases are skipped when dist/material-grub is not built)"""

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "dist/material-grub"
ASSEMBLE = ROOT / "install/bin/material-grub-assemble"
sys.path.insert(0, str(ROOT / "install/bin"))
import mgtheme


class Parse(unittest.TestCase):
    def test_parse_mode(self):
        self.assertEqual(mgtheme.parse_mode("1366x768"), (1366, 768))
        self.assertEqual(mgtheme.parse_mode("1366x768x32"), (1366, 768))
        for bad in ("", None, "auto", "keep", "banana", "99999x5", "100x100", "1366x", "x768"):
            self.assertIsNone(mgtheme.parse_mode(bad), bad)

    def test_first_mode(self):
        self.assertEqual(mgtheme.first_mode("1366x768,1280x720,auto"), (1366, 768))
        self.assertEqual(mgtheme.first_mode("auto,1280x720"), (1280, 720))
        self.assertIsNone(mgtheme.first_mode("auto"))
        self.assertIsNone(mgtheme.first_mode(""))

    def test_native_mode_from_drm(self):
        with tempfile.TemporaryDirectory() as d:
            for name, status, modes in (
                ("card0-eDP-1", "connected", "1366x768\n1280x720\n"),
                ("card0-HDMI-A-1", "disconnected", "3840x2160\n"),
                ("card0-DP-1", "connected", "1920x1080\n"),
            ):
                p = Path(d, name)
                p.mkdir()
                (p / "status").write_text(status + "\n")
                (p / "modes").write_text(modes)
            self.assertEqual(mgtheme.native_mode(d), (1920, 1080))  # the biggest connected one wins
        self.assertIsNone(mgtheme.native_mode("/nonexistent"))


class Anchor(unittest.TestCase):
    def test_exact_size_theme_is_centred(self):
        for W, H in ((1366, 768), (1280, 800), (2560, 1080), (1920, 1080)):
            t = mgtheme.theme_text(W, H, aspect="16x9")
            c = mgtheme.anchor_centre(t, W, H)
            self.assertNotEqual(t, c)
            self.assertIn("50%", c)
            # a plain pixel `left`/`top` is only left where it is 0 (a full-screen component)
            for m in re.finditer(r"(?m)^\s*(left|top) = (-?\d+)$", c):
                self.assertEqual(m[2], "0", m[0])

    def test_basic_theme_is_a_plain_list(self):
        t = mgtheme.basic_theme_text()
        self.assertIn("boot_menu", t)
        self.assertNotIn("desktop-image", t)


@unittest.skipUnless((PKG / "res/1920x1080").is_dir(), "package not built")
class Assemble(unittest.TestCase):
    def run_mode(self, mode):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run(
                [sys.executable, str(ASSEMBLE), "--mode", mode, "--pkg", str(PKG), "--out", d],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            return r.stdout.strip(), (Path(d) / "theme.txt").read_text(), r.stderr

    def test_exact_mode_is_printed_and_centred(self):
        for mode in ("1366x768", "1360x768", "1280x800", "2560x1080"):
            out, text, _ = self.run_mode(mode)
            self.assertEqual(out, mode)
            self.assertIn("50%", text)

    def test_depth_is_dropped(self):
        self.assertEqual(self.run_mode("1366x768x32")[0], "1366x768")

    def test_auto_is_the_1080p_theme(self):
        out, text, _ = self.run_mode("auto")
        self.assertEqual(out, "1920x1080")
        self.assertIn("boot_menu", text)

    def test_garbage_gets_the_basic_theme(self):
        for mode in ("keep", "banana", "99999x5"):
            out, text, err = self.run_mode(mode)
            self.assertEqual(out, "auto")
            self.assertNotIn("desktop-image", text)
            self.assertIn("basic", err)

    def test_basic_asked_for_is_silent(self):
        out, text, err = self.run_mode("basic")
        self.assertEqual(out, "auto")
        self.assertNotIn("desktop-image", text)
        self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
