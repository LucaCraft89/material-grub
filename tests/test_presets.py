"""Presets: save the current look, validate, apply on a fresh system, hostile files. stdlib only. usage: python3 tests/test_presets.py"""

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "install/bin"))
import mgoverrides  # noqa: E402
import mgpresets  # noqa: E402
import mgrub  # noqa: E402

OV = {
    "seed": {"mode": "single", "color": "#7E57C2"},
    "groups": ["windows", "linux"],
    "entries": [{"match": {"key": "fedora"}, "name": "Mine", "icon": "file:logo.png"}],
}


class Presets(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.root = Path(self.d.name)
        self.ov = self.root / "etc/material-grub/overrides.json"
        self.conf = self.root / "etc/material-grub.conf"
        self.conf.parent.mkdir(parents=True, exist_ok=True)
        self.conf.write_text("STYLE=list\nHINTS=off\n")
        mgoverrides.save(OV, self.ov)
        (self.ov.parent / "icons").mkdir()
        (self.ov.parent / "icons/logo.png").write_bytes(b"\x89PNG-not-really")

    def tearDown(self):
        self.d.cleanup()

    def test_save_list_and_roundtrip_to_another_machine(self):
        f = mgpresets.save("Gaming rig", self.ov, self.conf)
        self.assertEqual(f.name, "Gaming rig.json")
        self.assertEqual(mgpresets.listing(self.ov), [("Gaming rig", {"style": "list", "entries": 1})])
        data = mgpresets.load("Gaming rig", self.ov)
        self.assertEqual(base64.b64decode(data["icons"]["logo.png"]), b"\x89PNG-not-really")
        other = Path(tempfile.mkdtemp())
        ov2, conf2 = other / "etc/material-grub/overrides.json", other / "material-grub.conf"
        mgpresets.apply(data, ov2, conf2)
        self.assertEqual(mgoverrides.load(ov2)[0]["seed"]["color"], "#7E57C2")
        self.assertEqual(mgrub.load_conf(conf2)["STYLE"], "list")
        self.assertEqual((ov2.parent / "icons/logo.png").read_bytes(), b"\x89PNG-not-really")

    def test_scheme_is_not_part_of_a_preset(self):
        self.assertNotIn("SCHEME", mgpresets.build("x", self.ov, self.conf)["conf"])

    def test_bad_names(self):
        for n in ("", "../x", ".hidden", "a/b", "x" * 41, None):
            with self.assertRaises(ValueError):
                mgpresets.check_name(n)

    def test_hostile_presets_are_refused_and_change_nothing(self):
        good = mgpresets.build("ok", self.ov, self.conf)
        before = self.ov.read_text()
        bad = [
            dict(good, preset=2),
            dict(good, name="../../etc/passwd"),
            dict(good, conf={"STYLE": "neon"}),
            dict(good, conf={"EVIL": "on"}),
            dict(good, icons={"../../x.png": base64.b64encode(b"x").decode()}),
            dict(good, icons={"a.exe": base64.b64encode(b"x").decode()}),
            dict(good, icons={"a.png": "not base64!!"}),
            dict(good, overrides={"seed": {"mode": "x"}}),
            [],
        ]
        for b in bad:
            with self.assertRaises(ValueError, msg=str(b)[:80]):
                mgpresets.apply(b, self.ov, self.conf)
        self.assertEqual(self.ov.read_text(), before)
        self.assertEqual(mgrub.load_conf(self.conf)["STYLE"], "list")

    def test_delete(self):
        mgpresets.save("a", self.ov, self.conf)
        mgpresets.delete("a", self.ov)
        self.assertEqual(mgpresets.listing(self.ov), [])


if __name__ == "__main__":
    unittest.main()
