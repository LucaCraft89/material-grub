"""material_boot.seeds: the 32 preset colours and the terminal colour fallback."""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from material_boot import seeds  # noqa: E402


class Seeds(unittest.TestCase):
    def test_presets(self):
        self.assertEqual(len(seeds.SEEDS), 32)
        names = [n for n, _ in seeds.SEEDS]
        self.assertEqual(len(set(names)), 32)
        self.assertTrue(all(re.fullmatch(r"#[0-9A-F]{6}", h) for _, h in seeds.SEEDS))

    def test_name_of(self):
        h = seeds.SEEDS[5][1]
        self.assertEqual(seeds.name_of(h.lower()), seeds.SEEDS[5][0])
        self.assertIsNone(seeds.name_of("#123456"))

    def test_xterm256(self):
        self.assertEqual(seeds.xterm256("#000000"), 16)
        self.assertEqual(seeds.xterm256("#FFFFFF"), 231)
        self.assertEqual(seeds.xterm256("#FF0000"), 196)
        self.assertTrue(232 <= seeds.xterm256("#808080") <= 255)


if __name__ == "__main__":
    unittest.main()
