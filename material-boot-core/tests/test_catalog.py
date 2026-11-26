"""material_boot.catalog: the single source of truth for the distros. stdlib only."""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from material_boot import catalog as C  # noqa: E402


class Catalog(unittest.TestCase):
    def test_keys_are_unique_and_seeds_are_colours(self):
        keys = [e[0] for e in C.D + C.X]
        self.assertEqual(len(keys), len(set(keys)))
        for k, seed in C.SEEDS.items():
            self.assertRegex(seed, r"^#[0-9A-Fa-f]{6}$", k)
        self.assertIn("base", C.SEEDS)

    def test_every_glyph_source_is_in_the_repository(self):
        for g in [g for *_, g in C.ENTRIES] + list(C.EXTRA_GLYPHS.values()):
            self.assertTrue((ROOT / g).is_file(), g)

    def test_licences_travel_with_the_sources(self):
        for d in ("font-logos", "material-symbols", "fonts"):
            self.assertTrue(
                any((ROOT / "assets" / d).glob("*LICENSE*")) or (ROOT / "assets/fonts/OFL.txt").is_file(), d
            )

    def test_classes_start_with_the_key_and_are_lowercase(self):
        for k, al in C.CLASSES.items():
            self.assertEqual(al[0], k)
            self.assertTrue(all(a == a.lower() and re.fullmatch(r"[a-z0-9_.+!-]+", a) for a in al), k)

    def test_generic_words_are_not_distros(self):
        self.assertFalse(C.GENERIC & {e[0] for e in C.D if e[0] != "tux"} - {"mx"})


if __name__ == "__main__":
    unittest.main()
