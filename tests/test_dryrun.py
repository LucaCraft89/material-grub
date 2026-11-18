"""Unit tests for the pieces of `install.sh --dry-run` that need no root. The whole run is checked in containers
(tests/containers/dry_run.sh: Debian and Fedora, proving the system is byte-for-byte unchanged afterwards).
usage: python3 tests/test_dryrun.py"""

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault(
    "MATERIAL_OVERRIDES", "/nonexistent/material-grub/overrides.json"
)  # never the overrides of the machine running the tests
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "install/bin"))
import cmd_dryrun as dr  # noqa: E402


class Helpers(unittest.TestCase):
    def test_apply_sets_like_the_installer(self):
        text = "#STYLE=rail\nHINTS=on\n"
        out = dr.apply_sets(text, ["STYLE=list", "HINTS=off", "LOGO=off"])
        self.assertEqual(out, "STYLE=list\nHINTS=off\nLOGO=off\n")

    def test_gfxmode(self):
        self.assertEqual(dr.set_gfxmode("A=1\nGRUB_GFXMODE=auto\n", "1920x1080"), "A=1\nGRUB_GFXMODE=1920x1080\n")
        self.assertEqual(dr.set_gfxmode("A=1", "1920x1080"), "A=1\nGRUB_GFXMODE=1920x1080\n")

    def test_diff_is_empty_when_equal(self):
        self.assertEqual(dr.diff("/x", "a\n", "a\n", "new"), [])
        self.assertIn("+b\n", dr.diff("/x", "a\n", "a\nb\n", "new"))

    def test_summary_groups_the_package(self):
        files = ["/usr/share/material-grub/a", "/usr/share/material-grub/b", "/etc/grub.d/05_material"]
        s = dr.summarize(files)
        self.assertEqual(s, ["/usr/share/material-grub/ (the theme package)   [2 files]", "/etc/grub.d/05_material"])

    def test_not_root_lists_files_and_stops(self):
        if __import__("os").geteuid() == 0:
            self.skipTest("running as root")
        import subprocess

        pkg = ROOT / "dist/material-grub"
        if not (pkg / "res").is_dir():
            self.skipTest("no built package")
        r = subprocess.run(
            [
                sys.executable,
                str(ROOT / "install/bin/material-grub-dryrun"),
                "--pkg",
                str(pkg),
                "--res",
                "1920x1080",
                "--installer",
                str(ROOT / "install"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("Files the installer would write", r.stdout)
        self.assertIn("needs root", r.stdout)


if __name__ == "__main__":
    unittest.main()
