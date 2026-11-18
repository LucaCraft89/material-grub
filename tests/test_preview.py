"""Preview tests: scenes rendered for a sample menu into a self-contained page, no root and nothing installed.
Needs a built package (dist/material-grub). usage: python3 tests/test_preview.py"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "dist/material-grub"
BIN = ROOT / "install/bin"
sys.path.insert(0, str(BIN))
import cmd_preview  # noqa: E402


class Structure(unittest.TestCase):
    def test_entries_to_cfg_keeps_titles_classes_and_nesting(self):
        text = (
            "menuentry 'It''s a } {' --class a { echo }\nsubmenu 'Adv' --class b {\n menuentry 'k1' $x 'id' {\n }\n}\n"
        )
        out = cmd_preview.entries_to_cfg(text)
        import grubscript

        e = grubscript.scan(out).entries
        self.assertEqual(
            [(x.word, x.title, x.level) for x in e],
            [("menuentry", "Its a } {", "top"), ("submenu", "Adv", "top"), ("menuentry", "k1", "adv")],
        )
        self.assertEqual(e[0].classes, ["a"])


@unittest.skipUnless((PKG / "res/1920x1080").is_dir(), "no built package")
class Run(unittest.TestCase):
    def test_sample_page(self):
        with tempfile.TemporaryDirectory() as out:
            r = subprocess.run(
                [
                    sys.executable,
                    str(BIN / "material-grub-preview"),
                    "--pkg",
                    str(PKG),
                    "--res",
                    "1920x1080",
                    "--sample",
                    "--no-open",
                    "--out",
                    out,
                    "--style",
                    "list",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            page = (Path(out) / "index.html").read_text()
            self.assertIn("not GRUB itself", page)
            self.assertIn("Nothing was installed", page)
            self.assertGreaterEqual(page.count("data:image/png;base64,"), 7)
            self.assertGreaterEqual(len(list(Path(out).glob("*.png"))), 7)
            self.assertIn("/dev/sda5", page)  # the drive of the os-prober entry is in the caption
            self.assertIn("style list", page)


if __name__ == "__main__":
    unittest.main()
