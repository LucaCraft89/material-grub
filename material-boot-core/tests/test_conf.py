"""material_boot.conf: /etc/material-grub.conf, the settings every part shares. stdlib only. (Moved with the code from material-grub's tests/test_mgrub.py;
the assertions about applying the settings to a GRUB theme.txt stay there.)"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# the names in the tests below are kept as they were in material-grub
from material_boot import conf as mgrub  # noqa: E402


class Conf(unittest.TestCase):
    def test_conf(self):
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write('# c\nRAW_NAME=off\nCOUNTDOWN = "no"  # trailing\nLOGO=maybe\nTIMEOUT=12\nBOGUS=1\n')
            n = f.name
        c = mgrub.load_conf(n)
        os.unlink(n)
        self.assertEqual(
            (c["RAW_NAME"], c["COUNTDOWN"], c["LOGO"], c["TIMEOUT"]), ("off", "off", "on", "12")
        )  # bad value ignored
        self.assertNotIn("BOGUS", c)
        self.assertEqual(mgrub.load_conf("/nonexistent")["TIMEOUT"], "")

    def test_new_keys(self):
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write("STYLE=List\nHINTS=off\nCOOKIE=no\nSCHEME=sepia\n")
            n = f.name
        c = mgrub.load_conf(n)
        os.unlink(n)
        self.assertEqual(
            (c["STYLE"], c["HINTS"], c["COOKIE"], c["SCHEME"]), ("list", "off", "off", "dark")
        )  # bad SCHEME ignored
        d = mgrub.load_conf("/nonexistent")
        self.assertEqual((d["STYLE"], d["HINTS"], d["COOKIE"]), ("rail", "on", "on"))

    def test_plymouth_keys(self):
        d = mgrub.load_conf("/nonexistent")
        self.assertEqual((d["PLYMOUTH"], d["PLYMOUTH_BAR"], d["PLYMOUTH_MOTION"]), ("on", "indeterminate", "full"))
        with tempfile.TemporaryDirectory() as t:
            f = os.path.join(t, "c.conf")
            open(f, "w").write("PLYMOUTH=no\nPLYMOUTH_BAR=Progress\nPLYMOUTH_MOTION=sideways\n")
            c = mgrub.load_conf(f)
            self.assertEqual((c["PLYMOUTH"], c["PLYMOUTH_BAR"], c["PLYMOUTH_MOTION"]), ("off", "progress", "full"))
            mgrub.write_conf(f, {"PLYMOUTH_MOTION": "calm", "PLYMOUTH": "on"})
            self.assertEqual(mgrub.load_conf(f)["PLYMOUTH_MOTION"], "calm")
            for k, v in (("PLYMOUTH", "maybe"), ("PLYMOUTH_BAR", "wavy"), ("PLYMOUTH_MOTION", "")):
                with self.assertRaises(ValueError):
                    mgrub.write_conf(f, {k: v})

    def test_the_environment_variable_moves_the_file(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "c.conf"
            f.write_text("STYLE=clean\n")
            old = os.environ.get("MATERIAL_CONF")
            try:
                os.environ["MATERIAL_CONF"] = str(f)
                self.assertEqual(mgrub.load_conf()["STYLE"], "clean")
            finally:
                if old is None:
                    os.environ.pop("MATERIAL_CONF", None)
                else:
                    os.environ["MATERIAL_CONF"] = old


class WriteConf(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.d = tempfile.TemporaryDirectory()
        self.p = Path(self.d.name) / "material-grub.conf"

    def tearDown(self):
        self.d.cleanup()

    def test_replaces_sample_and_keeps_comments(self):
        self.p.write_text("# header\n#STYLE=rail\n#HINTS=on\n")
        mgrub.write_conf(self.p, {"STYLE": "list"})
        self.assertEqual(self.p.read_text(), "# header\nSTYLE=list\n#HINTS=on\n")

    def test_replaces_active_line_then_appends(self):
        self.p.write_text("STYLE=rail\n")
        mgrub.write_conf(self.p, {"STYLE": "split", "HINTS": "off"})
        self.assertEqual(self.p.read_text(), "STYLE=split\nHINTS=off\n")
        self.assertEqual(mgrub.load_conf(self.p)["STYLE"], "split")

    def test_creates_missing_file_and_keeps_mode(self):
        mgrub.write_conf(self.p, {"SCHEME": "light"})
        self.assertEqual(mgrub.load_conf(self.p)["SCHEME"], "light")
        self.p.chmod(0o600)
        mgrub.write_conf(self.p, {"TIMEOUT": "7"})
        self.assertEqual(self.p.stat().st_mode & 0o777, 0o600)

    def test_rejects_bad_values_without_writing(self):
        self.p.write_text("STYLE=rail\n")
        for bad in ({"STYLE": "neon"}, {"NOPE": "on"}, {"TIMEOUT": "x"}, {"HINTS": "maybe"}):
            with self.assertRaises(ValueError):
                mgrub.write_conf(self.p, bad)
        self.assertEqual(self.p.read_text(), "STYLE=rail\n")
        self.assertEqual([f.name for f in Path(self.d.name).iterdir()], [self.p.name])


if __name__ == "__main__":
    unittest.main()
