"""Monitor detection parsers against fixture outputs. stdlib only: python3 tests/test_monitors.py"""
import json, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "install")); import monitors as M

XRANDR = """Screen 0: minimum 320 x 200, current 4480 x 1440, maximum 16384 x 16384
eDP-1 connected 1920x1080+2560+0 (normal left inverted right x axis y axis) 344mm x 193mm
   1920x1080     60.01*+  59.97    59.96
   1680x1050     59.95
DP-2 connected primary 2560x1440+0+0 (normal left inverted right x axis y axis) 597mm x 336mm
   2560x1440     59.95*+
   1920x1080     60.00
HDMI-1 disconnected (normal left inverted right x axis y axis)
DP-3 connected (normal left inverted right x axis y axis)
   3840x2160     30.00 +
"""
KSCREEN = json.dumps({"outputs": [{"name": "DP-1", "enabled": True, "priority": 1, "currentModeId": "1", "modes": [{"id": "1", "size": {"width": 3840, "height": 2160}}]},
    {"name": "HDMI-A-1", "enabled": True, "priority": 2, "currentModeId": "2", "modes": [{"id": "2", "size": {"width": 1920, "height": 1080}}]},
    {"name": "DP-2", "enabled": False, "priority": 0, "currentModeId": "3", "modes": [{"id": "3", "size": {"width": 800, "height": 600}}]}]})
WLR = """eDP-1 "Sharp (eDP-1)"
  Enabled: yes
  Modes:
    2880x1800 px, 120.000 Hz (preferred, current)
    1920x1200 px, 60.000 Hz
HDMI-A-1 "Dell"
  Enabled: no
  Modes:
    1920x1080 px, 60.000 Hz (preferred)
"""
MUTTER = ("(uint32 3, [(('eDP-1', 'BOE', '0x0a68', '0x00000000'), [('2256x1504@59.999', 2256, 1504, 59.999, 1.0, [1.0, 2.0], {'is-current': <true>, 'is-preferred': <true>}), "
          "('1920x1080@60.0', 1920, 1080, 60.0, 1.0, [1.0], {})], {'is-builtin': <true>})], [(0, 0, 1.0, uint32 0, true, [('eDP-1', 'BOE', '0x0a68', '0x00000000')], {})], {})")

class Parsers(unittest.TestCase):
    def test_xrandr(self):
        o = M.parse_xrandr(XRANDR); self.assertEqual([(x["name"], x["w"], x["h"], x["primary"]) for x in o],
            [("eDP-1", 1920, 1080, False), ("DP-2", 2560, 1440, True), ("DP-3", 3840, 2160, False)])   # DP-3: no current mode, preferred one used; HDMI-1 disconnected
    def test_kscreen(self):
        o = M.parse_kscreen(KSCREEN); self.assertEqual([(x["name"], x["w"], x["primary"]) for x in o], [("DP-1", 3840, True), ("HDMI-A-1", 1920, False)])
        self.assertEqual(M.parse_kscreen("not json"), [])
    def test_wlr(self):
        o = M.parse_wlr_randr(WLR); self.assertEqual([(x["name"], x["w"], x["h"], x["primary"]) for x in o], [("eDP-1", 2880, 1800, True)])
    def test_mutter(self):
        o = M.parse_mutter(MUTTER); self.assertEqual([(x["name"], x["w"], x["h"], x["primary"]) for x in o], [("eDP-1", 2256, 1504, True)])
    def test_drm_internal_first(self):
        with tempfile.TemporaryDirectory() as d:
            for name, status, modes in (("card0-DP-1", "connected", "3840x2160\n1920x1080\n"), ("card0-eDP-1", "connected", "1920x1200\n"), ("card0-HDMI-A-1", "disconnected", "")):
                p = Path(d) / name; p.mkdir(); (p / "status").write_text(status + "\n"); (p / "modes").write_text(modes)
            o = M.parse_drm(d); self.assertEqual([x["name"] for x in o if x["primary"]], ["eDP-1"])
            for n in ("card0-eDP-1",): (Path(d) / n / "status").write_text("disconnected\n")
            o = M.parse_drm(d); self.assertEqual([(x["name"], x["w"]) for x in o if x["primary"]], [("DP-1", 3840)])   # no panel: largest output
    def test_gfxmode_and_fallback(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f: f.write('GRUB_TIMEOUT=5\nGRUB_GFXMODE="2560x1440,auto"\n')
        self.assertEqual((M.grub_gfxmode(f.name)["w"], M.grub_gfxmode(f.name)["h"]), (2560, 1440)); self.assertIsNone(M.grub_gfxmode("/nonexistent"))
        with tempfile.TemporaryDirectory() as d: c = M.detect(d, "/nonexistent")
        self.assertTrue(c and c[0]["w"] > 0)

if __name__ == "__main__": unittest.main()
