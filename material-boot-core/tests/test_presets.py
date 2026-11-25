"""material_boot.presets: save the current look, validate, apply on a fresh system, hostile files. stdlib only. (Moved with the code from material-grub.)"""

import base64
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# the names in the tests below are kept as they were in material-grub
from material_boot import conf as mgrub  # noqa: E402
from material_boot import overrides as mgoverrides  # noqa: E402
from material_boot import presets as mgpresets  # noqa: E402

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

    def test_the_plymouth_look_travels_with_a_preset(self):
        mgrub.write_conf(self.conf, {"PLYMOUTH_BAR": "progress", "PLYMOUTH_MOTION": "calm", "PLYMOUTH": "off"})
        mgpresets.save("Calm", self.ov, self.conf)
        data = mgpresets.load("Calm", self.ov)
        self.assertEqual(
            {k: data["conf"][k] for k in ("PLYMOUTH", "PLYMOUTH_BAR", "PLYMOUTH_MOTION")},
            {"PLYMOUTH": "off", "PLYMOUTH_BAR": "progress", "PLYMOUTH_MOTION": "calm"},
        )
        other = Path(tempfile.mkdtemp())
        ov2, conf2 = other / "etc/material-grub/overrides.json", other / "material-grub.conf"
        mgpresets.apply(data, ov2, conf2)
        c = mgrub.load_conf(conf2)
        self.assertEqual((c["PLYMOUTH"], c["PLYMOUTH_BAR"], c["PLYMOUTH_MOTION"]), ("off", "progress", "calm"))

    def test_a_preset_from_before_the_plymouth_keys_still_applies(self):
        old = mgpresets.build("Old", self.ov, self.conf)
        for k in ("PLYMOUTH", "PLYMOUTH_BAR", "PLYMOUTH_MOTION"):
            old["conf"].pop(k, None)
        clean, errs = mgpresets.validate(old)
        self.assertEqual(errs, [])
        other = Path(tempfile.mkdtemp())
        mgpresets.apply(old, other / "o/overrides.json", other / "m.conf")
        self.assertEqual(mgrub.load_conf(other / "m.conf")["PLYMOUTH_MOTION"], "full")

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
