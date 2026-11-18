"""overrides.json through material-grub-scenes: custom colour, name, icon, single seed, and a broken file falling back. Needs a built package + Pillow.
usage: python3 tests/test_custom.py"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "dist/material-grub"
BIN = ROOT / "install/bin"
sys.path.insert(0, str(BIN))
ENTRIES = [
    {
        "class": "mg_aaaaaaaaaa",
        "key": "fedora",
        "kind": "kernel",
        "level": "top",
        "title": "Fedora Linux 6.1",
        "kver": "6.1",
    },
    {"class": "mg_bbbbbbbbbb", "key": "windows11", "kind": "plain", "level": "top", "title": "Windows Boot Manager"},
    {"class": "mg_cccccccccc", "key": "ubuntu", "kind": "kernel", "level": "top", "title": "Ubuntu"},
]


def rgb(h):
    return tuple(int(h[i : i + 2], 16) for i in (1, 3, 5))


@unittest.skipUnless((PKG / "subtitles.json").is_file(), "no built package with subtitles.json")
class Custom(unittest.TestCase):
    def setUp(self):
        from PIL import Image

        self.Image = Image
        self.d = Path(tempfile.mkdtemp())
        self.theme = self.d / "theme"
        subprocess.run(
            [sys.executable, BIN / "material-grub-assemble", "--mode", "1920x1080", "--pkg", PKG, "--out", self.theme],
            check=True,
            capture_output=True,
        )
        self.state = self.d / "state/entries.json"
        self.state.parent.mkdir()
        self.state.write_text(json.dumps(ENTRIES))
        self.state.with_name("menu.json").write_text(
            json.dumps([{"level": "top", "items": [e["class"] for e in ENTRIES]}])
        )
        (self.d / "mg.conf").write_text("STYLE=rail\n")
        self.ov = self.d / "etc/overrides.json"
        self.ov.parent.mkdir()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def bake(self, ov=None, raw=None, style="rail"):
        (self.d / "mg.conf").write_text(f"STYLE={style}\n")
        if ov is not None:
            self.ov.write_text(json.dumps(ov))
        if raw is not None:
            self.ov.write_text(raw)
        env = dict(os.environ, MATERIAL_CONF=str(self.d / "mg.conf"), MATERIAL_OVERRIDES=str(self.ov))
        r = subprocess.run(
            [sys.executable, BIN / "material-grub-scenes", "--theme", self.theme, "--pkg", PKG, "--state", self.state],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def scene(self, cls):
        return self.Image.open(self.theme / "icons" / f"{cls}.png").convert("RGB")

    def test_custom_colour_only_changes_that_entry(self):
        import mgpalette

        self.bake()
        base_f, base_u = self.scene("mg_aaaaaaaaaa"), self.scene("mg_cccccccccc")
        self.bake({"entries": [{"match": {"key": "fedora"}, "color": "#E95420"}]})
        f, u = self.scene("mg_aaaaaaaaaa"), self.scene("mg_cccccccccc")
        self.assertEqual(u.tobytes(), base_u.tobytes())
        self.assertNotEqual(f.tobytes(), base_f.tobytes())
        self.assertEqual(f.getpixel((f.width - 3, 3)), rgb(mgpalette.scheme("#E95420", True)["surface"]))

    def test_single_seed_recolours_everything(self):
        import mgpalette

        out = self.bake({"seed": {"mode": "single", "color": "#7E57C2"}})
        want = rgb(mgpalette.scheme("#7E57C2", True)["surface"])
        for cls in ("mg_aaaaaaaaaa", "mg_cccccccccc"):
            im = self.scene(cls)
            self.assertEqual(im.getpixel((im.width - 3, 3)), want, cls)
        self.assertIn("entry scenes", out)

    def test_custom_name_gives_a_plain_entry_its_own_scene(self):
        self.bake()
        base = self.scene("windows11")  # the shared class scene a plain entry uses
        self.assertFalse((self.theme / "icons/mg_bbbbbbbbbb.png").exists())
        self.bake({"entries": [{"match": {"title": "windows"}, "name": "Work PC"}]})
        self.assertNotEqual(self.scene("mg_bbbbbbbbbb").tobytes(), base.tobytes())  # now it has its own scene

    def test_user_icon_png(self):
        self.bake()
        base = self.scene("mg_cccccccccc")
        icons = self.ov.parent / "icons"
        icons.mkdir()
        self.Image.new("RGBA", (64, 64), (200, 30, 30, 255)).save(icons / "mine.png")
        self.bake({"entries": [{"match": {"key": "ubuntu"}, "icon": "file:mine.png"}]})
        self.assertNotEqual(self.scene("mg_cccccccccc").tobytes(), base.tobytes())

    def test_unreadable_icon_keeps_default(self):
        self.bake()
        base = self.scene("mg_cccccccccc")
        out = self.bake({"entries": [{"match": {"key": "ubuntu"}, "icon": "file:missing.png"}]})
        self.assertIn("cannot read the icon", out)
        self.assertEqual(self.scene("mg_cccccccccc").tobytes(), base.tobytes())

    def test_broken_overrides_fall_back_to_defaults(self):
        self.bake()
        base = self.scene("mg_aaaaaaaaaa").tobytes()
        out = self.bake(raw="{broken")
        self.assertIn("overrides:", out)
        self.assertEqual(self.scene("mg_aaaaaaaaaa").tobytes(), base)

    def test_other_styles_still_render(self):
        for style in ("clean", "list", "split"):
            self.bake({"entries": [{"match": {"key": "fedora"}, "color": "#2E7D32", "name": "Mine"}]}, style=style)
            self.assertEqual(self.scene("mg_aaaaaaaaaa").size, (1920, 1080), style)


if __name__ == "__main__":
    unittest.main()
