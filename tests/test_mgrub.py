"""Unit tests for the entry-title parser and name matcher. stdlib only: python3 tests/test_mgrub.py"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "install/bin"))
import mgrub


class Parse(unittest.TestCase):
    def test_bls(self):
        d = mgrub.parse_title("Fedora Linux (7.3.3-200.fc44.x86_64) 44 (Workstation Edition)")
        self.assertEqual(
            (d["os"], d["kver"], d["osver"], d["edition"]),
            ("Fedora Linux", "7.3.3-200.fc44.x86_64", "44", "Workstation Edition"),
        )

    def test_ostree(self):
        d = mgrub.parse_title("Fedora Linux 44.20260301.0 (Silverblue) (ostree:0)")
        self.assertEqual(
            (d["os"], d["osver"], d["edition"], d["kver"]), ("Fedora Linux", "44.20260301.0", "Silverblue", "ostree:0")
        )

    def test_classic(self):
        d = mgrub.parse_title("Ubuntu, with Linux 6.8.0-45-generic (recovery mode)")
        self.assertEqual((d["os"], d["kver"], d["edition"]), ("Ubuntu", "6.8.0-45-generic", "recovery mode"))

    def test_osprober(self):
        d = mgrub.parse_title("Ubuntu 24.04.1 LTS (on /dev/sda5)")
        self.assertEqual((d["os"], d["osver"], d["where"]), ("Ubuntu", "24.04.1 LTS", "/dev/sda5"))


class Kind(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(mgrub.kind_of("Advanced options for Debian", "debian", True), "advanced")
        self.assertEqual(mgrub.kind_of("Fedora Linux (0-rescue-abc) 44", "fedora"), "rescue")
        self.assertEqual(mgrub.kind_of("Windows Boot Manager", "windows11"), "plain")
        self.assertEqual(mgrub.kind_of("Arch Linux", "arch"), "kernel")


def _rules():  # generated from the catalog exactly as package.py does it
    sys.path.insert(0, str(ROOT / "scripts"))
    import re

    import catalog as C

    rules = []
    for k, title, _, _, _, _, al in C.D:
        for p in {
            title,
            k,
            *[a for a in al if a not in {"os", "gnu", "gnu-linux", "unknown", "win", "mx", "nix", "linux"}],
        }:
            toks = re.findall(r"[a-z0-9]+", p.lower())
            if toks:
                rules.append({"key": k, "tokens": toks})
    return sorted(rules, key=lambda r: -len("".join(r["tokens"])))


class Match(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = _rules()

    def test_known(self):
        for title, key in [
            ("CachyOS Linux", "cachyos"),
            ("Linux Mint 22", "linuxmint"),
            ("Pop!_OS 24.04", "pop"),
            ("openSUSE Tumbleweed", "opensuse"),
            ("Fedora Linux (6.8) 44", "fedora"),
            ("KALI GNU/LINUX", "kali"),
            ("EndeavourOS", "endeavouros"),
            ("Kubuntu 24.04", "kubuntu"),
        ]:
            self.assertEqual(mgrub.key_for(title, self.rules), key, title)

    def test_unknown_and_windows(self):
        self.assertIsNone(mgrub.key_for("Some Unknown OS", self.rules))
        self.assertIsNone(
            mgrub.key_for("Windows Boot Manager", self.rules)
        )  # Windows is resolved separately (10 vs 11)


class Bls(unittest.TestCase):
    def test_calls(self):
        c = mgrub.bls_call
        self.assertEqual(c("blscfg"), ("", ""))
        self.assertEqual(c("\t  blscfg  # load"), ("\t  ", ""))
        self.assertEqual(c("    blscfg --enable-fallback"), ("    ", "--enable-fallback"))
        for no in ("insmod blscfg", "if blscfg; then true; fi", "set blsdir=/x", "# blscfg", "blscfgx"):
            self.assertIsNone(c(no), no)
        self.assertTrue(mgrub.bls_restructurable(c("blscfg")))
        self.assertTrue(mgrub.bls_restructurable(c("blscfg --enable-fallback")))
        for opt in ("--path /loader/entries", "--show-default", "--show-non-default"):
            self.assertFalse(mgrub.bls_restructurable(c("blscfg " + opt)), opt)


class Conf(unittest.TestCase):
    def test_conf(self):
        import os
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write('# c\nRAW_NAME=off\nCOUNTDOWN = "no"  # trailing\nLOGO=maybe\nTIMEOUT=12\nBOGUS=1\n')
            n = f.name
        c = mgrub.load_conf(n)
        os.unlink(n)
        self.assertEqual(
            (c["RAW_NAME"], c["COUNTDOWN"], c["LOGO"], c["TIMEOUT"]), ("off", "off", "on", "12")
        )  # bad value ignored
        self.assertEqual(mgrub.load_conf("/nonexistent")["TIMEOUT"], "")
        t = "a\n# mg:begin raw\nX\n# mg:end raw\n# mg:begin logo\nY\n# mg:end logo\nb\n"
        self.assertEqual(mgrub.apply_conf_to_theme(t, c), "a\n# mg:begin logo\nY\n# mg:end logo\nb\n")

    def test_new_keys(self):
        import os
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write("STYLE=List\nHINTS=off\nCOOKIE=no\nSCHEME=sepia\n")
            n = f.name
        c = mgrub.load_conf(n)
        os.unlink(n)
        self.assertEqual(
            (c["STYLE"], c["HINTS"], c["COOKIE"], c["SCHEME"]), ("list", "off", "off", "dark")
        )  # bad SCHEME ignored
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write("STYLE=split\n")
            n = f.name
        self.assertEqual(mgrub.load_conf(n)["STYLE"], "split")
        os.unlink(n)
        d = mgrub.load_conf("/nonexistent")
        self.assertEqual((d["STYLE"], d["HINTS"], d["COOKIE"]), ("rail", "on", "on"))
        t = "# mg:begin logo\nY\n# mg:end logo\nb\n"
        self.assertEqual(mgrub.apply_conf_to_theme(t, c), "b\n", "COOKIE=off removes the logo block too")


class Catalog(unittest.TestCase):
    def test_catalog(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import catalog as C

        keys = [r[0] for r in C.D]
        self.assertEqual(len(keys), len(set(keys)), "duplicate keys")
        for k, _title, _sub, glyph, seed, src, al in C.D:
            self.assertRegex(k, r"^[a-z0-9]+$")
            self.assertRegex(seed, r"^#[0-9A-Fa-f]{6}$")
            self.assertIn(src, ("chosen", "si", "proposed"))
            self.assertTrue(glyph is None or (ROOT / glyph).exists(), f"{k}: missing glyph {glyph}")
            self.assertTrue(all(a == a.lower() for a in al), f"{k}: aliases must be lowercase")


if __name__ == "__main__":
    unittest.main()
