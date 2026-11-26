"""material_boot.palette: the vendored colour science gives the 14 roles of a seed. (That the vendored copy equals the pinned pip release the theme build
uses is checked in material-grub, which owns the build.)"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from material_boot import palette as mgpalette  # noqa: E402


class Palette(unittest.TestCase):
    def test_shape(self):
        for dark in (True, False):
            p = mgpalette.scheme("#0B3D2E", dark)
            self.assertEqual(tuple(p), mgpalette.ROLES)
            self.assertTrue(all(re.fullmatch(r"#[0-9A-F]{6}", v) for v in p.values()))

    def test_dark_and_light_differ(self):
        dark, light = mgpalette.scheme("#E95420", True), mgpalette.scheme("#E95420", False)
        self.assertNotEqual(dark["surface"], light["surface"])

    def test_grey_seed_is_grey(self):
        for v in mgpalette.scheme("#808080", True).values():
            r, g, b = (int(v[i : i + 2], 16) for i in (1, 3, 5))
            self.assertLessEqual(max(r, g, b) - min(r, g, b), 2)

    def test_known_value(self):  # the green seed of the theme: matches the build's primary
        self.assertEqual(mgpalette.scheme("#0B3D2E", True)["primary"], "#E7FFF2")


if __name__ == "__main__":
    unittest.main()
