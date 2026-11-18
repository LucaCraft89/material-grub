"""mgscenes.Renderer.panel_scene (the build-time panels redrawn at config time) must match what the build baked. Needs a built package. usage: python3 tests/test_panel.py"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "dist/material-grub"
sys.path.insert(0, str(ROOT / "install/bin"))


def mean_diff(a, b):
    from PIL import ImageChops

    h = ImageChops.difference(a, b).convert("L").histogram()
    return sum(i * c for i, c in enumerate(h)) / sum(h)


@unittest.skipUnless((PKG / "subtitles.json").is_file() and (PKG / "scenes/16x9/bg").is_dir(), "no built package with subtitles.json")
class PanelScene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import mgscenes
        from PIL import Image

        cls.Image = Image
        cls.R = mgscenes.Renderer(PKG, 1080)
        cls.titles = json.loads((PKG / "titles.json").read_text())
        cls.subs = json.loads((PKG / "subtitles.json").read_text())
        cls.classes = json.loads((PKG / "classes.json").read_text())

    def test_bg_is_pixel_identical(self):
        for key in ("fedora", "windows11", "firmware"):
            bg = self.Image.open(PKG / f"scenes/16x9/bg/{key}.png").convert("RGB")
            self.assertEqual(mean_diff(bg, self.R.panel_scene(bg.size, key, hero=False)), 0, key)

    def test_hero_scene_is_close(self):  # the glyph is resampled from a 512 px mask, the build rasterises the SVG at size
        for key in ("fedora", "ubuntu", "arch"):
            ic = self.Image.open(PKG / f"scenes/16x9/icons/{self.classes[key][0]}.png").convert("RGB")
            mine = self.R.panel_scene(ic.size, key, self.titles[key], self.subs[key], hero=True)
            self.assertLess(mean_diff(ic, mine), 0.05, key)

    def test_custom_palette_changes_the_colours(self):
        import mgpalette

        bg = self.Image.open(PKG / "scenes/16x9/bg/fedora.png").convert("RGB")
        p = mgpalette.scheme("#E95420", True)
        mine = self.R.panel_scene(bg.size, "fedora", hero=False, p=p)
        self.assertEqual(mine.getpixel((5, bg.height // 2)), tuple(int(p["surface"][i : i + 2], 16) for i in (1, 3, 5)))


if __name__ == "__main__":
    unittest.main()
