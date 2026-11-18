"""Unit tests for the entry-title parser and name matcher. stdlib only: python3 tests/test_mgrub.py"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "install/bin"))
import mgrub


class SharedLists(unittest.TestCase):
    """The resolution list and the GENERIC alias set each live in one place; any copy that appears again fails here."""

    def sources(self):
        for pat in (
            "install.sh",
            "install/*.py",
            "install/*.sh",
            "install/bin/*.py",
            "install/bin/material-grub-*",
            "scripts/*.py",
        ):
            yield from ROOT.glob(pat)

    def test_no_second_resolution_list(self):
        for f in self.sources():
            text = f.read_text()
            self.assertNotIn("1280x720 1920x1080", text, f"{f}: a hard-coded resolution list; read mgrub.RESOLUTIONS")
            self.assertNotIn('"1280x720", "1920x1080", "1920x1200"', text, f"{f}: a hard-coded resolution list")

    def test_no_second_generic_set(self):
        for f in self.sources():
            if f.name == "mgrub.py":
                continue
            self.assertNotIn("GENERIC = {", f.read_text(), f"{f}: a copy of mgrub.GENERIC")

    def test_resolution_list_shape(self):
        res = mgrub.RESOLUTIONS
        self.assertEqual(len(res), len(set(res)))
        for r in res:
            w, h = map(int, r.split("x"))
            self.assertGreater(w, h)

    def test_docs_list_every_resolution(self):
        readme = (ROOT / "docs/install.md").read_text()
        for r in mgrub.RESOLUTIONS:
            self.assertIn(f"`{r}`", readme, f"docs/install.md does not list {r}")

    def test_package_uses_the_shared_list(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        text = (ROOT / "scripts/package.py").read_text()
        self.assertIn("RES_ALL = mgrub.RESOLUTIONS", text)
        self.assertIn("GENERIC = mgrub.GENERIC", text)

    def test_snap(self):
        self.assertEqual(mgrub.snap("1920x1080"), "1920x1080")
        self.assertEqual(mgrub.snap("1600x1000"), "1920x1200")
        self.assertEqual(mgrub.snap("1366x768"), "1280x720")
        self.assertEqual(mgrub.snap("1000x1000", ["1920x1080", "1920x1200"]), "1920x1080")


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


class Requirements(unittest.TestCase):
    """requirements.txt is exact and hashed: pip install --require-hashes refuses anything else."""

    def test_every_pin_is_exact_and_hashed(self):
        import re

        text = (ROOT / "requirements.txt").read_text().replace("\\\n", " ")
        reqs = [l for l in text.splitlines() if l.strip() and not l.startswith("#")]
        self.assertGreaterEqual(len(reqs), 3)
        for l in reqs:
            self.assertRegex(l, r"^[A-Za-z0-9_.-]+==[0-9][^\s;]* ")
            self.assertGreaterEqual(len(re.findall(r"--hash=sha256:[0-9a-f]{64}", l)), 1, l[:60])

    def test_covers_the_direct_requirements(self):
        text = (ROOT / "requirements.txt").read_text().lower()
        for name in ("fonttools==", "pillow==", "materialyoucolor=="):
            self.assertIn(name, text)


class DrivePill(unittest.TestCase):
    """Two installs of one distro (os-prober) must be told apart: the drive shows in the info pills."""

    def test_where_is_a_pill(self):
        import mgscenes

        a = {**mgrub.parse_title("Ubuntu 24.04.1 LTS (on /dev/sda5)"), "kind": "kernel", "title": "x"}
        b = {**mgrub.parse_title("Ubuntu 22.04 LTS (on /dev/nvme0n1p3)"), "kind": "kernel", "title": "y"}
        pa = [t for t, *_ in mgscenes.Renderer.info_pills(a)]
        pb = [t for t, *_ in mgscenes.Renderer.info_pills(b)]
        self.assertIn("/dev/sda5", pa)
        self.assertIn("/dev/nvme0n1p3", pb)
        self.assertNotEqual(pa, pb)
        self.assertEqual(
            mgscenes.Renderer.info_pills({"kind": "plain", "title": "W", "where": "/dev/sdb1"})[0][0], "/dev/sdb1"
        )
        self.assertEqual(mgscenes.Renderer.info_pills({"kind": "plain", "title": "W"}), [])

    def test_list_label_names_the_drive_for_duplicates(self):
        import mgscenes

        r = mgscenes.Renderer.__new__(mgscenes.Renderer)
        r.titles = {"ubuntu": "Ubuntu"}
        e = {"kind": "kernel", "key": "ubuntu", "level": "top", "title": "x", "where": "/dev/sda5", "dup_where": True}
        self.assertEqual(r.label_for(e), "Ubuntu (sda5)")
        e.pop("dup_where")
        self.assertEqual(r.label_for(e), "Ubuntu")

    def test_distinct_classes_per_drive(self):
        self.assertNotEqual(mgrub.uid("top", "Ubuntu (on /dev/sda5)"), mgrub.uid("top", "Ubuntu (on /dev/sdb5)"))


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
