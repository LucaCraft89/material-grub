"""material_boot.scenes.Renderer.panel_scene (the build-time panels redrawn at config time) must match what the build baked. Needs a built material-grub package: MATERIAL_PKG=<dir> (skipped without)."""

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = Path(os.environ.get("MATERIAL_PKG", "/nonexistent/material-grub-package"))
sys.path.insert(0, str(ROOT))

try:
    from material_boot import scenes as mgscenes_mod  # noqa: E402
except ImportError:  # no Pillow: the renderer cannot be imported, and these tests cannot run
    mgscenes_mod = None


def mean_diff(a, b):
    from PIL import ImageChops

    h = ImageChops.difference(a, b).convert("L").histogram()
    return sum(i * c for i, c in enumerate(h)) / sum(h)


@unittest.skipUnless(
    mgscenes_mod is not None and (PKG / "subtitles.json").is_file() and (PKG / "scenes/16x9/bg").is_dir(),
    "no Pillow, or no built package with subtitles.json (set MATERIAL_PKG)",
)
class PanelScene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PIL import Image

        from material_boot import scenes as mgscenes

        cls.Image = Image
        cls.R = mgscenes.Renderer(PKG, 1080)
        cls.titles = json.loads((PKG / "titles.json").read_text())
        cls.subs = json.loads((PKG / "subtitles.json").read_text())
        cls.classes = json.loads((PKG / "classes.json").read_text())

    def test_bg_is_pixel_identical(self):
        for key in ("fedora", "windows11", "firmware"):
            bg = self.Image.open(PKG / f"scenes/16x9/bg/{key}.png").convert("RGB")
            self.assertEqual(mean_diff(bg, self.R.panel_scene(bg.size, key, hero=False)), 0, key)

    def test_hero_scene_is_close(
        self,
    ):  # the glyph is resampled from a 512 px mask, the build rasterises the SVG at size
        for key in ("fedora", "ubuntu", "arch"):
            ic = self.Image.open(PKG / f"scenes/16x9/icons/{self.classes[key][0]}.png").convert("RGB")
            mine = self.R.panel_scene(ic.size, key, self.titles[key], self.subs[key], hero=True)
            self.assertLess(mean_diff(ic, mine), 0.05, key)

    def test_a_square_picture_fits_inside_its_card(self):
        sq = self.Image.new("RGBA", (500, 500), (30, 160, 30, 255))
        wide = self.Image.new("RGBA", (800, 200), (30, 160, 30, 255))
        fitted = self.R.fit_logo(sq, 440, 240)
        self.assertLessEqual(fitted.height, 240)
        self.assertEqual(fitted.width, fitted.height)  # the proportions are kept
        self.assertEqual(self.R.fit_logo(wide, 440, 240).size, (440, 110))  # a wide logo still fills the width
        self.assertEqual(self.R.fit_logo(wide, 440).size, (440, 110))

    def test_custom_palette_changes_the_colours(self):
        from material_boot import palette as mgpalette

        bg = self.Image.open(PKG / "scenes/16x9/bg/fedora.png").convert("RGB")
        p = mgpalette.scheme("#E95420", True)
        mine = self.R.panel_scene(bg.size, "fedora", hero=False, p=p)
        self.assertEqual(mine.getpixel((5, bg.height // 2)), tuple(int(p["surface"][i : i + 2], 16) for i in (1, 3, 5)))

    def test_firmware_logo_is_drawn_in_the_cookie_of_previews_only(self):
        import tempfile

        from PIL import Image

        bmp = Path(tempfile.mkdtemp()) / "bgrt.bmp"
        im = Image.new("RGB", (80, 60), (255, 255, 255))
        im.paste((0, 0, 0), (20, 15, 60, 45))
        im.save(bmp, "BMP")
        logo = mgscenes_mod.machine_logo(PKG, 120, src=str(bmp))
        self.assertEqual(logo.size, (120, 120))
        self.assertGreater(logo.getchannel("A").getpixel((60, 60)), 200)  # the silhouette is in the middle
        self.assertIsNone(mgscenes_mod.machine_logo(PKG, 120, src="/nonexistent/bgrt", fallback=False))
        tux = mgscenes_mod.machine_logo(PKG, 120, src="/nonexistent/bgrt")  # no firmware logo: the penguin
        self.assertEqual(tux.size, (120, 120))
        self.assertGreater(tux.getchannel("A").getbbox()[2], 40)
        p = self.R.pal["fedora"]
        plain = self.Image.new("RGBA", (1920, 1080))
        self.R.draw_cookie(plain, p)
        with_logo = self.Image.new("RGBA", (1920, 1080))
        self.R.preview_logo = logo
        try:
            self.R.draw_cookie(with_logo, p)
        finally:
            self.R.preview_logo = None
        c = (1920 - 150, 140)
        self.assertNotEqual(plain.getpixel(c), with_logo.getpixel(c))
        self.assertEqual(plain.getpixel((5, 5)), with_logo.getpixel((5, 5)))


if __name__ == "__main__":
    unittest.main()
